#Requires -Version 5.1
[CmdletBinding()]
param([switch]$SelfTest,[switch]$InstallWslTools,[string]$IsoPath = '',[string]$IsoSha256 = '')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
function Assert-Hash([string]$Expected) {
 if ($Expected.Length -ne 64 -or $Expected -match '[^a-fA-F0-9]') { throw 'Expected a verified SHA256 checksum' }
}
function Resolve-ApprovedHash([string]$Provided,[string]$ChecksumFile) {
 if ($Provided) { Assert-Hash $Provided; return $Provided.ToUpperInvariant() }
 if (-not (Test-Path -LiteralPath $ChecksumFile -PathType Leaf)) {
  throw 'BLOCKED: supply independently authenticated -IsoSha256 or mint-source.sha256'
 }
 $value = (Get-Content -LiteralPath $ChecksumFile -Raw).Trim()
 Assert-Hash $value
 return $value.ToUpperInvariant()
}
function Assert-Source([string]$Path,[string]$Hash) {
 Assert-Hash $Hash
 if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw 'Mint ISO not found' }
 if ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -ne $Hash.ToUpperInvariant()) { throw 'Mint ISO checksum mismatch' }
}
function Test-DedicatedVmListed([string]$Listing) {
 return [bool]($Listing -match '(?m)^"Canopy-Test-Mint"\s+\{[0-9a-fA-F-]{36}\}\s*$')
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
 if ((Resolve-ApprovedHash ('b' * 64) 'C:\missing-checksum-file') -ne ('B' * 64)) { throw 'Explicit verified hash rejected' }
 $blocked = $false
 try { Resolve-ApprovedHash '' 'C:\missing-checksum-file' | Out-Null } catch { $blocked = $true }
 if (-not $blocked) { throw 'Missing authenticated checksum accepted' }
 if (-not (Test-DedicatedVmListed '"Canopy-Test-Mint" {12345678-1234-1234-1234-123456789abc}')) { throw 'Existing VM not detected' }
 if (Test-DedicatedVmListed '"Other-VM" {12345678-1234-1234-1234-123456789abc}') { throw 'Unrelated VM detected as Canopy' }
 if ((Get-VMAction $false $false) -ne 'create') { throw 'VM creation decision regression' }
 if ((Get-VMAction $true $true) -ne 'reuse') { throw 'Existing VM decision regression' }
 $blocked = $false
 try { Get-VMAction $false $true | Out-Null } catch { $blocked = $true }
 if (-not $blocked) { throw 'Orphaned virtual disk accepted' }
 'PASS: one-click cache provenance and VM isolation tests'
 exit 0
}
$base = Join-Path $env:LOCALAPPDATA 'CanopyTestLab'
$iso = if ($IsoPath) { $IsoPath } else { Join-Path $env:USERPROFILE 'Downloads\linuxmint-22.3-cinnamon-64bit (1).iso' }
$hashFile = Join-Path $PSScriptRoot 'mint-source.sha256'
$expected = Resolve-ApprovedHash $IsoSha256 $hashFile
Assert-Source $iso $expected
function Get-ResumeCommand([string]$Launcher) {
 if (-not [IO.Path]::IsPathRooted($Launcher) -or -not (Test-Path -LiteralPath $Launcher -PathType Leaf)) { throw 'Unsafe resume launcher path' }
 if ($Launcher -match '"') { throw 'Unsafe quote in resume launcher path' }
 return ('"' + $Launcher + '"')
}
function Register-CanopyResume {
 $launcher = Join-Path $PSScriptRoot 'Canopy-OneClick.cmd'
 $command = Get-ResumeCommand $launcher
 if ($IsoPath -or $IsoSha256) { throw 'BLOCKED: custom ISO arguments cannot yet be preserved across restart; no automatic resume registered' }
 $key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce'
 if (-not (Test-Path -LiteralPath $key)) { New-Item -Path $key -Force | Out-Null }
 New-ItemProperty -Path $key -Name 'CanopyResumeSetup' -Value $command -PropertyType String -Force | Out-Null
 Write-Host 'Canopy will resume at your next Windows sign-in. No automatic restart was requested.'
}
function Clear-CanopyResume {
 Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce' -Name 'CanopyResumeSetup' -ErrorAction SilentlyContinue
}
# Bootstrap WSL automatically when possible. A required Windows reboot is reported,
# never forced, and no VM is modified before the Linux builder is ready.
function Test-WslReady {
 $wslCommand = Get-Command wsl.exe -ErrorAction SilentlyContinue
 if (-not $wslCommand) { return $false }
 & wsl.exe --exec bash -c 'exit 0' 2>$null | Out-Null
 return ($LASTEXITCODE -eq 0)
}
if (-not (Test-WslReady)) {
 $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
 $principal = New-Object Security.Principal.WindowsPrincipal($identity)
 if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  $arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath + '"'
  if ($IsoPath) { $arguments += ' -IsoPath "' + $IsoPath.Replace('"','') + '"' }
  if ($IsoSha256) { $arguments += ' -IsoSha256 ' + $IsoSha256 }
  $arguments += ' -InstallWslTools'
  $elevated = Start-Process -FilePath 'powershell.exe' -ArgumentList $arguments -Verb RunAs -Wait -PassThru
  if ($elevated.ExitCode -ne 0) { throw ('BLOCKED: elevated setup exited with code ' + $elevated.ExitCode) }
  exit 0
 }
 if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) { throw 'BLOCKED: wsl.exe unavailable; Windows servicing is required before bootstrap' }
 Write-Host 'Installing WSL Ubuntu prerequisite (Windows may require a restart)...'
 & wsl.exe --install -d Ubuntu --no-launch
 if (-not (Test-WslReady)) {
  Register-CanopyResume
  throw 'BLOCKED: WSL requires a restart or first-run initialization; setup will retry at next sign-in. VM unchanged.'
 }
}
Clear-CanopyResume
& wsl.exe --exec bash -c 'command -v xorriso >/dev/null && command -v python3 >/dev/null && command -v openssl >/dev/null && command -v sha256sum >/dev/null' | Out-Null
if ($LASTEXITCODE -ne 0) {
 Write-Host 'Installing missing ISO-building tools in WSL...'
 & wsl.exe --user root --exec apt-get update
 if ($LASTEXITCODE -ne 0) { throw 'BLOCKED: WSL package installation failed or root account unavailable. VM unchanged.' }
 & wsl.exe --user root --exec apt-get install -y --no-install-recommends xorriso python3 openssl coreutils
 if ($LASTEXITCODE -ne 0) { throw 'BLOCKED: WSL package installation failed. VM unchanged.' }
 & wsl.exe --exec bash -c 'command -v xorriso >/dev/null && command -v python3 >/dev/null && command -v openssl >/dev/null && command -v sha256sum >/dev/null' | Out-Null
 if ($LASTEXITCODE -ne 0) { throw 'BLOCKED: ISO-building tools remain unavailable.' }
}
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
$exists = Test-DedicatedVmListed ($vmList | Out-String)
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
