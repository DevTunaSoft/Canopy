#Requires -Version 5.1
<#
.SYNOPSIS
One-entry-point, fail-closed Canopy Mint lab provisioning.
By default: preflight only. -Provision requires verified local ISO and explicit consent.
#>
[CmdletBinding()]
param(
 [string]$IsoPath = '',
 [string]$IsoSha256 = '',
 [string]$PasswordFile = '',
 [switch]$Provision,
 [switch]$ConfigureUnattended,
 [switch]$SelfTest
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
function Assert-CanopySetupOptions {
 param([bool]$Provisioning,[bool]$Unattended,[string]$Iso,[string]$Hash,[string]$Secret)
 if ($Unattended -and -not $Provisioning) { throw 'ConfigureUnattended requires Provision' }
 if ($Provisioning -and (-not $Iso -or $Hash -notmatch '^[a-fA-F0-9]{64}$')) {
   throw 'Provisioning requires a local verified ISO path and independently authenticated SHA256'
 }
 if ($Unattended -and -not $Secret) { throw 'Unattended setup requires a protected local password file' }
}
if ($SelfTest) {
 Assert-CanopySetupOptions $false $false '' '' ''
 $blocked = $false
 try { Assert-CanopySetupOptions $false $true '' '' '' } catch { $blocked = $true }
 if (-not $blocked) { throw 'Unattended opt-in bypass' }
 $blocked = $false
 try { Assert-CanopySetupOptions $true $false 'mint.iso' 'wrong' '' } catch { $blocked = $true }
 if (-not $blocked) { throw 'ISO verification bypass' }
 Write-Output 'PASS: one-entry-point consent and verification gates'
 exit 0
}
Assert-CanopySetupOptions ([bool]$Provision) ([bool]$ConfigureUnattended) $IsoPath $IsoSha256 $PasswordFile
$preflight = Join-Path $PSScriptRoot 'Test-CanopyHost.ps1'
if (-not (Test-Path -LiteralPath $preflight -PathType Leaf)) { throw 'Missing host preflight' }
$reportText = & $preflight
if ($LASTEXITCODE -ne 0) { throw 'Host preflight blocked; no VM changes made' }
$report = ($reportText | Out-String | ConvertFrom-Json)
if ($report.status -ne 'PASS') { throw 'Host preflight did not pass' }
Write-Output 'PASS: Windows host prerequisites'
if (-not $Provision) {
 Write-Output 'No VM created. For provisioning supply -Provision, -IsoPath and independently authenticated -IsoSha256.'
 exit 0
}
$creator = Join-Path $PSScriptRoot 'New-CanopyMintVM.ps1'
& $creator -IsoPath $IsoPath -IsoSha256 $IsoSha256 -Create
if ($LASTEXITCODE -ne 0) { throw 'VM hardware creation failed; inspect state before retry' }
Write-Output 'PASS: dedicated VM hardware created; Mint not yet installed'
if (-not $ConfigureUnattended) {
 Write-Output 'STOP: unattended configuration was not authorized'
 exit 0
}
$installer = Join-Path $PSScriptRoot 'Install-CanopyMintOS.ps1'
& $installer -IsoPath $IsoPath -IsoSha256 $IsoSha256 -PasswordFile $PasswordFile -Install
if ($LASTEXITCODE -ne 0) { throw 'Unattended configuration failed; no Mint boot verified' }
Write-Output 'Unattended setup configured. Guest installation, boot and Cinnamon login remain unverified.'
