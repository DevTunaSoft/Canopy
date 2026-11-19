#Requires -Version 5.1
<#
.SYNOPSIS
One-click disposable Canopy VM installation orchestrator.
Requires pre-existing WSL Linux with xorriso, python3, openssl, and a verified
Mint ISO. Fails closed rather than silently installing Windows components.
#>
[CmdletBinding()]
param([switch]$SelfTest)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$base = Join-Path $env:LOCALAPPDATA 'CanopyTestLab'
$logs = Join-Path $base 'diagnostics'
New-Item -ItemType Directory -Force -Path $logs | Out-Null
function Assert-Source([string]$Iso,[string]$Expected) {
 if (-not (Test-Path -LiteralPath $Iso -PathType Leaf)) { throw 'Linux Mint ISO missing from Downloads' }
 if ($Expected -notmatch '^[a-fA-F0-9]{64}$') { throw 'Missing independently authenticated official ISO checksum' }
 if ((Get-FileHash -LiteralPath $Iso -Algorithm SHA256).Hash -ne $Expected.ToUpperInvariant()) {
  throw 'Linux Mint source ISO SHA256 mismatch'
 }
}
function Assert-PreparedCache([string]$Image,[string]$Receipt,[string]$SourceHash) {
 if (-not (Test-Path -LiteralPath $Image -PathType Leaf)) { return $false }
 if (-not (Test-Path -LiteralPath $Receipt -PathType Leaf)) {
  throw 'Prepared ISO exists without a provenance receipt. Refusing unverified cached installer.'
 }
 $record = Get-Content -LiteralPath $Receipt -Raw | ConvertFrom-Json
 if ($record.source_sha256 -ne $SourceHash.ToUpperInvariant()) {
  throw 'Prepared ISO was built from a different Mint source; refusing stale installer.'
 }
 if ($record.prepared_sha256 -notmatch '^[a-fA-F0-9]{64}$'
 -or
     (Get-FileHash -LiteralPath $Image -Algorithm SHA256).Hash -ne $record.prepared_sha256) {
  throw 'Prepared ISO does not match its recorded checksum; refusing modified installer.'
 }
 return $true
}
function Get-WslPath([string]$Path) {
 $result = & wsl.exe wslpath -a -u $Path
 if ($LASTEXITCODE -ne 0 -or -not $result) { throw 'WSL cannot resolve Windows file path' }
 return ($result | Select-Object -First 1).Trim()
}
if ($SelfTest) {
 $blocked = $false
 try { Assert-Source 'C:\missing.iso' ('a' * 64) } catch { $blocked = $true }
 if (-not $blocked) { throw 'Missing source accepted' }
 $tempImage = Join-Path $env:TEMP ('canopy-cache-test-' + [guid]::NewGuid().ToString('N') + '.iso')
 try {
  [IO.File]::WriteAllText($tempImage, 'test')
  $blocked = $false
  try { Assert-PreparedCache $tempImage ($tempImage + '.json') ('a' * 64) | Out-Null } catch { $blocked = $true }
  if (-not $blocked) { throw 'Prepared ISO without receipt was accepted' }
  $actual = (Get-FileHash -LiteralPath $tempImage -Algorithm SHA256).Hash
  @{source_sha256=('a' * 64);prepared_sha256=$actual} | ConvertTo-Json | Set-Content -LiteralPath ($tempImage + '.json')
  if (-not (Assert-PreparedCache $tempImage ($tempImage + '.json') ('a' * 64))) { throw 'Valid cache rejected' }
  [IO.File]::WriteAllText($tempImage, 'tampered')
  $blocked = $false
  try { Assert-PreparedCache $tempImage ($tempImage + '.json') ('a' * 64) | Out-Null } catch { $blocked = $true }
  if (-not $blocked) { throw 'Tampered ISO was accepted' }
 } finally {
  Remove-Item -LiteralPath $tempImage,($tempImage + '.json') -Force -ErrorAction SilentlyContinue
 }
 'PASS: source and prepared ISO provenance regression gates'
 exit 0
}
$repo = $PSScriptRoot
$iso = Join-Path $env:USERPROFILE 'Downloads\linuxmint-22.3-cinnamon-64bit (1).iso'
$hashFile = Join-Path $repo 'mint-source.sha256'
if (-not (Test-Path -LiteralPath $hashFile -PathType Leaf)) {
 throw 'BLOCKED: mint-source.sha256 missing. Supply the independently verified official Mint ISO checksum in this file.'
}
$expected = (Get-Content -LiteralPath $hashFile -Raw).Trim()
Assert-Source $iso $expected
$wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
if (-not $wsl) { throw 'BLOCKED: WSL Linux is not installed. No VM changes made.' }
& wsl.exe --exec bash -c 'command -v xorriso && command -v python3 && command -v openssl && command -v sha256sum' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'BLOCKED: WSL Linux needs xorriso, python3, openssl and sha256sum. No VM changes made.' }
$preparedDir = Join-Path $base 'prepared'
New-Item -ItemType Directory -Path $preparedDir -Force | Out-Null
$prepared = Join-Path $preparedDir 'canopy-mint-test.iso'
$builder = Join-Path $repo 'scripts\Build-CanopyMintUnattendedISO.sh'
if (-not (Test-Path -LiteralPath $builder -PathType Leaf)) { throw 'ISO builder missing' }
$receipt = $prepared + '.json'
if (-not (Assert-PreparedCache $prepared $receipt $expected)) {
 $linuxBuilder = Get-WslPath $builder
 $linuxIso = Get-WslPath $iso
 $linuxPrepared = Get-WslPath $prepared
 & wsl.exe --exec bash $linuxBuilder $linuxIso $expected $linuxPrepared
 if ($LASTEXITCODE -ne 0) { throw 'Mint ISO remaster failed. VM was not modified.' }
 $builtHash = (Get-FileHash -LiteralPath $prepared -Algorithm SHA256).Hash
 @{source_sha256=$expected.ToUpperInvariant();prepared_sha256=$builtHash} | ConvertTo-Json | Set-Content -LiteralPath $receipt -Encoding UTF8
}
if (-not (Assert-PreparedCache $prepared $receipt $expected)) { throw 'Prepared ISO validation failed' }
$preparedHash = (Get-FileHash -LiteralPath $prepared -Algorithm SHA256).Hash
$vbox = Join-Path $env:ProgramFiles 'Oracle\VirtualBox\VBoxManage.exe'
if (-not (Test-Path -LiteralPath $vbox -PathType Leaf)) { throw 'VirtualBox missing' }
& $vbox showvminfo 'Canopy-Test-Mint' '--machinereadable' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'BLOCKED: existing dedicated Canopy-Test-Mint VM missing; no other VM will be changed.' }
$attach = Join-Path $repo 'scripts\Attach-CanopyPreparedISO.ps1'
& $attach -IsoPath $prepared -IsoSha256 $preparedHash -Start
if (-not $?) { throw 'VirtualBox attachment/start failed' }
'Canopy VM started. Installation completion and desktop boot are not yet verified.'