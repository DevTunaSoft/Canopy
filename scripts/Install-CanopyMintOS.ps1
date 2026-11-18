#Requires -Version 5.1
<#
.SYNOPSIS
Opt-in VirtualBox unattended Mint installation attempt on dedicated VM only.
Dry-run by default. VirtualBox/Mint compatibility must be verified on hardware.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$IsoPath,
  [Parameter(Mandatory=$true)][string]$IsoSha256,
  [Parameter(Mandatory=$true)][string]$PasswordFile,
  [string]$VBoxManage = '',
  [switch]$Install,
  [switch]$SelfTest
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
function Get-CanopyUnattendedArgs {
  param([string]$Iso, [string]$Secret)
  return @('unattended','install','Canopy-Test-Mint',
           ('--iso=' + $Iso),'--user=canopy-test',
           ('--user-password-file=' + $Secret),
           '--no-install-additions')
}
if ($SelfTest) {
  $argsToCheck = @(Get-CanopyUnattendedArgs 'C:\mint.iso' 'C:\private-password.txt')
  if ($argsToCheck.Count -ne 7 -or $argsToCheck[2] -ne 'Canopy-Test-Mint' -or
      $argsToCheck[4] -ne '--user=canopy-test' -or
      $argsToCheck[5] -ne '--user-password-file=C:\private-password.txt') {
    throw 'Unattended argument contract failed'
  }
  Write-Output 'PASS: dedicated unattended install argument contract'
  exit 0
}
if ($IsoSha256 -notmatch '^[0-9a-fA-F]{64}$') { throw 'Expected independently authenticated SHA256' }
$iso = (Resolve-Path -LiteralPath $IsoPath -ErrorAction Stop).ProviderPath
if (-not $iso.EndsWith('.iso',[StringComparison]::OrdinalIgnoreCase)) { throw 'Expected ISO file' }
if ((Get-FileHash -LiteralPath $iso -Algorithm SHA256).Hash -ne $IsoSha256.ToUpperInvariant()) {
  throw 'ISO checksum mismatch'
}
$secret = (Resolve-Path -LiteralPath $PasswordFile -ErrorAction Stop).ProviderPath
if ((Get-Item -LiteralPath $secret).Length -lt 1 -or
    (Get-Item -LiteralPath $secret).Length -gt 128) {
  throw 'Password file must contain 1–128 bytes'
}
if (-not $VBoxManage) { $VBoxManage = Join-Path $env:ProgramFiles 'Oracle\VirtualBox\VBoxManage.exe' }
if (-not (Test-Path -LiteralPath $VBoxManage -PathType Leaf)) { throw 'VirtualBox is not installed' }
$info = & $VBoxManage showvminfo 'Canopy-Test-Mint' '--machinereadable'
if ($LASTEXITCODE -ne 0) { throw 'Dedicated VM not found' }
if (($info | Out-String) -notmatch '(?m)^VMState="poweroff"\s*$') {
  throw 'Dedicated VM must be powered off'
}
$argsToRun = @(Get-CanopyUnattendedArgs $iso $secret)
# Always probe without modifying guest first. This is NOT proof Mint can boot.
& $VBoxManage @($argsToRun + @('--dry-run')) | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'VirtualBox rejected unattended dry-run for this ISO' }
if (-not $Install) {
  Write-Output 'DRY RUN passed. Mint is NOT installed. Explicit -Install required.'
  exit 0
}
& $VBoxManage @argsToRun | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Unattended configuration failed; inspect VM state' }
Write-Output 'Unattended configuration accepted. Start the dedicated VM and verify actual Mint installation and boot.'
