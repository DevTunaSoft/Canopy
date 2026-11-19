#Requires -Version 5.1
[CmdletBinding()]
param([switch]$SelfTest)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
function Assert-Hash([string]$Expected) {
 if ($Expected.Length -ne 64 -or $Expected -match '[^a-fA-F0-9]') { throw 'Expected a verified SHA256 checksum' }
}
function Assert-Source([string]$Path,[string]$Hash) {
 Assert-Hash $Hash
 if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw 'Mint ISO not found' }
 if ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -ne $Hash.ToUpperInvariant()) { throw 'Mint ISO checksum mismatch' }
}
function Get-VMAction([bool]$Exists,[bool]$DedicatedDiskExists) {
 if ($Exists) { return 'reuse' }
 if ($DedicatedDiskExists) { throw 'Orphaned dedicated virtual disk exists; refusing to overwrite it' }
 return 'create'
}
function Assert-Cache([string]$Image,[string]$Receipt,[string]$SourceHash) {
 if (-not (Test-Path -LiteralPath $Image -PathType Leaf)) { return $false }
 if (-not (Test-Path -LiteralPath $Receipt -PathType Leaf)) { throw 'Prepared ISO has no provenance receipt' }
 $record = Get-Content -LiteralPath $Receipt -Raw | ConvertFrom-Json
 Assert-Hash $record.prepared_sha256
 if ($record.source_sha256 -ne $SourceHash.ToUpperInvariant()) { throw 'Stale source checksum' }
 if ((Get-FileHash -LiteralPath $Image -Algorithm SHA256).Hash -ne $record.prepared_sha256.ToUpperInvariant()) { throw 'Prepared ISO checksum mismatch' }
 return $true
}
if ($SelfTest) {
 $test = Join-Path $env:TEMP ('canopy-' + [guid]::NewGuid().ToString('N') + '.iso')
 $receipt = $test + '.json'
 try {
  [IO.File]::WriteAllText($test,'valid')
  $hash = (Get-FileHash -LiteralPath $test -Algorithm SHA256).Hash
  $blocked = $false
  try { Assert-Cache $test $receipt ('a' * 64) | Out-Null } catch { $blocked = $true }
  if (-not $blocked) { throw 'Missing receipt accepted' }
  @{source_sha256=('a' * 64);prepared_sha256=$hash} | ConvertTo-Json | Set-Content -LiteralPath $receipt
  if (-not (Assert-Cache $test $receipt ('a' * 64))) { throw 'Valid receipt rejected' }
  [IO.File]::WriteAllText($test,'tampered')
  $blocked = $false
  try { Assert-Cache $test $receipt ('a' * 64) | Out-Null } catch { $blocked = $true }
  if (-not $blocked) { throw 'Tampered image accepted' }
 } finally { Remove-Item -LiteralPath $test,$receipt -Force -ErrorAction SilentlyContinue }
 if ((Get-VMAction $false $false) -ne 'create') { throw 'VM creation decision regression' }
 if ((Get-VMAction $true $true) -ne 'reuse') { throw 'Existing VM decision regression' }
 $blocked = $false
 try { Get-VMAction $false $true | Out-Null } catch { $blocked = $true }
 if (-not $blocked) { throw 'Orphaned virtual disk accepted' }
 'PASS: one-click cache provenance and VM isolation tests'
 exit 0
}
$base = Join-Path $env:LOCALAPPDATA 'CanopyTestLab'
$iso = Join-Path $env:USERPROFILE 'Downloads\linuxmint-22.3-cinnamon-64bit (1).iso'
$hashFile = Join-Path $PSScriptRoot 'mint-source.sha256'
if (-not (Test-Path -LiteralPath $hashFile -PathType Leaf)) { throw 'BLOCKED: authenticated Mint checksum file missing' }
$expected = (Get-Content -LiteralPath $hashFile -Raw).Trim()
Assert-Source $iso $expected
if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) { throw 'BLOCKED: WSL missing' }
& wsl.exe --exec bash -c 'command -v xorriso && command -v python3 && command -v openssl && command -v sha256sum' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'BLOCKED: WSL image-building dependencies missing' }
$directory = Join-Path $base 'prepared'
New-Item -ItemType Directory -Force -Path $directory | Out-Null
$prepared = Join-Path $directory 'canopy-mint-test.iso'
$receipt = $prepared + '.json'
if (-not (Assert-Cache $prepared $receipt $expected)) {
 $builder = Join-Path $PSScriptRoot 'scripts\Build-CanopyMintUnattendedISO.sh'
 $linuxBuilder = (& wsl.exe wslpath -a -u $builder | Select-Object -First 1).Trim()
 $linuxIso = (& wsl.exe wslpath -a -u $iso | Select-Object -First 1).Trim()
 $linuxPrepared = (& wsl.exe wslpath -a -u $prepared | Select-Object -First 1).Trim()
 & wsl.exe --exec bash $linuxBuilder $linuxIso $expected $linuxPrepared
 if ($LASTEXITCODE -ne 0) { throw 'Mint remaster failed; VM unchanged' }
 $hash = (Get-FileHash -LiteralPath $prepared -Algorithm SHA256).Hash
 @{source_sha256=$expected.ToUpperInvariant();prepared_sha256=$hash} | ConvertTo-Json | Set-Content -LiteralPath $receipt
}
if (-not (Assert-Cache $prepared $receipt $expected)) { throw 'Prepared ISO verification failed' }
$vbox = Join-Path $env:ProgramFiles 'Oracle\VirtualBox\VBoxManage.exe'
if (-not (Test-Path -LiteralPath $vbox -PathType Leaf)) { throw 'VirtualBox missing' }
$vmList = @(& $vbox list vms)
if ($LASTEXITCODE -ne 0) { throw 'Unable to enumerate VirtualBox VMs' }
$exists = [bool](($vmList | Out-String) -match '(?m)^"Canopy-Test-Mint"\\s')
$disk = Join-Path $base 'VirtualMachines\\Canopy-Test-Mint.vdi'
$action = Get-VMAction $exists (Test-Path -LiteralPath $disk)
if ($action -eq 'create') {
 $creator = Join-Path $PSScriptRoot 'scripts\\New-CanopyMintVM.ps1'
 & $creator -IsoPath $prepared -IsoSha256 (Get-FileHash -LiteralPath $prepared -Algorithm SHA256).Hash -Create
 if (-not $?) { throw 'Dedicated VM creation failed' }
}
& $vbox showvminfo 'Canopy-Test-Mint' '--machinereadable' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Dedicated test VM unavailable' }
$attach = Join-Path $PSScriptRoot 'scripts\Attach-CanopyPreparedISO.ps1'
& $attach -IsoPath $prepared -IsoSha256 (Get-FileHash -LiteralPath $prepared -Algorithm SHA256).Hash -Start
if (-not $?) { throw 'VM launch failed' }
'VM launched; actual Mint installation and desktop boot remain unverified.'
