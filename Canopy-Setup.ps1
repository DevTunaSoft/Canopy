#Requires -Version 5.1
<#
.SYNOPSIS
Single-file Windows entry point for Canopy Mint test-lab setup.
Run from any directory. Downloads a pinned GitHub branch using Git, then
orchestrates the guarded host and VM scripts. Does not claim a completed OS install.
#>
[CmdletBinding()]
param(
 [string]$IsoPath = '',
 [string]$IsoUrl = '',
 [string]$IsoSha256 = '',
 [string]$PasswordFile = '',
 [switch]$CreateVM,
 [switch]$ConfigureUnattended,
 [switch]$StartVM,
 [switch]$SelfTest
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repository = 'https://github.com/DevTunaSoft/Canopy.git'
$branch = 'fix/testlab-replay-proof-transport'
$vm = 'Canopy-Test-Mint'
function Get-VerifiedMintIso {
 param([string]$Url,[string]$ExpectedHash,[string]$Destination)
 if ($ExpectedHash -notmatch '^[0-9a-fA-F]{64}
 param([bool]$Create,[bool]$Unattended,[bool]$Start,[string]$Iso,[string]$Hash,[string]$Secret,[string]$Url = '')
 if ($Unattended -and -not $Create) { throw 'Unattended requires CreateVM' }
 if ($Start -and -not $Unattended) { throw 'StartVM requires unattended configuration in this run' }
 if ($Iso -and $Url) { throw 'Specify either IsoPath or IsoUrl, not both' }
 if ($Create -and ((-not $Iso -and -not $Url) -or $Hash -notmatch '^[0-9a-fA-F]{64}
   throw 'Creating a VM requires local ISO and independently authenticated SHA256'
 }
 if ($Unattended -and -not $Secret) { throw 'Protected password file required' }
}
if ($SelfTest) {
 Assert-Options $false $false $false '' '' ''
 $blocked = $false
 try { Assert-Options $false $false $true '' '' '' } catch { $blocked = $true }
 if (-not $blocked) { throw 'Start without installation was accepted' }
 Write-Output 'PASS: standalone bootstrap safety gates'
 exit 0
}
Assert-Options ([bool]$CreateVM) ([bool]$ConfigureUnattended) ([bool]$StartVM) $IsoPath $IsoSha256 $PasswordFile $IsoUrl
$git = Get-Command git.exe -ErrorAction SilentlyContinue
if ($null -eq $git) { throw 'Git for Windows required: https://git-scm.com/downloads/win' }
$base = Join-Path $env:LOCALAPPDATA 'CanopyTestLab'
$checkout = Join-Path $base 'source'
if (-not (Test-Path -LiteralPath $checkout)) {
 New-Item -ItemType Directory -Path $base -Force | Out-Null
 & $git.Source clone '--depth=1' '--single-branch' '--branch' $branch $repository $checkout
 if ($LASTEXITCODE -ne 0) { throw 'Repository checkout failed' }
} else {
 if (-not (Test-Path -LiteralPath (Join-Path $checkout '.git'))) { throw 'Existing source path is not a Git checkout' }
 $origin = (& $git.Source -C $checkout remote get-url origin | Out-String).Trim()
 if ($LASTEXITCODE -ne 0 -or $origin -ne $repository) { throw 'Existing source checkout has unexpected origin; refusing to run' }
 $currentBranch = (& $git.Source -C $checkout branch '--show-current' | Out-String).Trim()
 if ($currentBranch -ne $branch) { throw 'Existing checkout is on unexpected branch' }
 $dirty = (& $git.Source -C $checkout status '--porcelain=v1' '--untracked-files=all' | Out-String).Trim()
 if ($LASTEXITCODE -ne 0 -or $dirty) { throw 'Existing source checkout is dirty; refusing to run' }
 & $git.Source -C $checkout pull '--ff-only'
 if ($LASTEXITCODE -ne 0) { throw 'Could not safely update checkout' }
}
$launcher = Join-Path $checkout 'scripts\Start-CanopyTestLab.ps1'
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) { throw 'Missing Canopy launcher' }
if (-not $CreateVM) {
 & $launcher
 if ($LASTEXITCODE -ne 0) { throw 'Host preflight blocked' }
 Write-Output 'Host ready. Mint ISO verification and VM creation not started.'
 exit 0
}
if ($IsoUrl) {
 $IsoPath = Get-VerifiedMintIso -Url $IsoUrl -ExpectedHash $IsoSha256 -Destination (Join-Path $base 'downloads\linuxmint-canopy.iso')
}
& $launcher -Provision -IsoPath $IsoPath -IsoSha256 $IsoSha256 -ConfigureUnattended:$ConfigureUnattended -PasswordFile $PasswordFile
if ($LASTEXITCODE -ne 0) { throw 'VM provisioning failed' }
if (-not $StartVM) { exit 0 }
$vbox = Join-Path $env:ProgramFiles 'Oracle\VirtualBox\VBoxManage.exe'
if (-not (Test-Path -LiteralPath $vbox -PathType Leaf)) { throw 'VirtualBox CLI missing' }
& $vbox startvm $vm '--type=headless'
if ($LASTEXITCODE -ne 0) { throw 'VM start failed; inspect guest state' }
Write-Output 'VM started. Mint installation and Cinnamon login remain UNVERIFIED.'
) { throw 'Independently authenticated SHA256 required before download' }
 $uri = $null
 if (-not [Uri]::TryCreate($Url,[UriKind]::Absolute,[ref]$uri) -or
     $uri.Scheme -ne 'https' -or $uri.UserInfo -or $uri.Fragment) {
   throw 'ISO URL must be a clean HTTPS address'
 }
 if (-not $uri.AbsolutePath.EndsWith('.iso',[StringComparison]::OrdinalIgnoreCase)) {
   throw 'Download URL must end in .iso'
 }
 $parent = Split-Path -Parent $Destination
 New-Item -ItemType Directory -Path $parent -Force | Out-Null
 if (Test-Path -LiteralPath $Destination -PathType Leaf) {
   if ((Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash -eq $ExpectedHash.ToUpperInvariant()) {
     Write-Output 'Reusing already verified ISO'
     return $Destination
   }
   throw 'Existing ISO checksum differs; refusing overwrite'
 }
 $temporary = Join-Path $parent ('mint-download-' + [guid]::NewGuid().ToString('N') + '.part')
 try {
   Write-Output 'Downloading Mint ISO over HTTPS; validating complete file SHA256 before use'
   Invoke-WebRequest -Uri $uri.AbsoluteUri -OutFile $temporary -MaximumRedirection 5 -ErrorAction Stop
   $actual = (Get-FileHash -LiteralPath $temporary -Algorithm SHA256).Hash
   if ($actual -ne $ExpectedHash.ToUpperInvariant()) { throw 'Downloaded ISO SHA256 mismatch; file rejected' }
   if (Test-Path -LiteralPath $Destination) { throw 'ISO destination appeared during download; refusing overwrite' }
   Move-Item -LiteralPath $temporary -Destination $Destination -ErrorAction Stop
   return $Destination
 } finally {
   if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
 }
}
function Assert-Options {
 param([bool]$Create,[bool]$Unattended,[bool]$Start,[string]$Iso,[string]$Hash,[string]$Secret)
 if ($Unattended -and -not $Create) { throw 'Unattended requires CreateVM' }
 if ($Start -and -not $Unattended) { throw 'StartVM requires unattended configuration in this run' }
 if ($Create -and (-not $Iso -or $Hash -notmatch '^[0-9a-fA-F]{64}$')) {
   throw 'Creating a VM requires local ISO and independently authenticated SHA256'
 }
 if ($Unattended -and -not $Secret) { throw 'Protected password file required' }
}
if ($SelfTest) {
 Assert-Options $false $false $false '' '' ''
 $blocked = $false
 try { Assert-Options $false $false $true '' '' '' } catch { $blocked = $true }
 if (-not $blocked) { throw 'Start without installation was accepted' }
 Write-Output 'PASS: standalone bootstrap safety gates'
 exit 0
}
Assert-Options ([bool]$CreateVM) ([bool]$ConfigureUnattended) ([bool]$StartVM) $IsoPath $IsoSha256 $PasswordFile
$git = Get-Command git.exe -ErrorAction SilentlyContinue
if ($null -eq $git) { throw 'Git for Windows required: https://git-scm.com/downloads/win' }
$base = Join-Path $env:LOCALAPPDATA 'CanopyTestLab'
$checkout = Join-Path $base 'source'
if (-not (Test-Path -LiteralPath $checkout)) {
 New-Item -ItemType Directory -Path $base -Force | Out-Null
 & $git.Source clone '--depth=1' '--single-branch' '--branch' $branch $repository $checkout
 if ($LASTEXITCODE -ne 0) { throw 'Repository checkout failed' }
} else {
 if (-not (Test-Path -LiteralPath (Join-Path $checkout '.git'))) { throw 'Existing source path is not a Git checkout' }
 $origin = (& $git.Source -C $checkout remote get-url origin | Out-String).Trim()
 if ($LASTEXITCODE -ne 0 -or $origin -ne $repository) { throw 'Existing source checkout has unexpected origin; refusing to run' }
 $currentBranch = (& $git.Source -C $checkout branch '--show-current' | Out-String).Trim()
 if ($currentBranch -ne $branch) { throw 'Existing checkout is on unexpected branch' }
 $dirty = (& $git.Source -C $checkout status '--porcelain=v1' '--untracked-files=all' | Out-String).Trim()
 if ($LASTEXITCODE -ne 0 -or $dirty) { throw 'Existing source checkout is dirty; refusing to run' }
 & $git.Source -C $checkout pull '--ff-only'
 if ($LASTEXITCODE -ne 0) { throw 'Could not safely update checkout' }
}
$launcher = Join-Path $checkout 'scripts\Start-CanopyTestLab.ps1'
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) { throw 'Missing Canopy launcher' }
if (-not $CreateVM) {
 & $launcher
 if ($LASTEXITCODE -ne 0) { throw 'Host preflight blocked' }
 Write-Output 'Host ready. Mint ISO verification and VM creation not started.'
 exit 0
}
& $launcher -Provision -IsoPath $IsoPath -IsoSha256 $IsoSha256 -ConfigureUnattended:$ConfigureUnattended -PasswordFile $PasswordFile
if ($LASTEXITCODE -ne 0) { throw 'VM provisioning failed' }
if (-not $StartVM) { exit 0 }
$vbox = Join-Path $env:ProgramFiles 'Oracle\VirtualBox\VBoxManage.exe'
if (-not (Test-Path -LiteralPath $vbox -PathType Leaf)) { throw 'VirtualBox CLI missing' }
& $vbox startvm $vm '--type=headless'
if ($LASTEXITCODE -ne 0) { throw 'VM start failed; inspect guest state' }
Write-Output 'VM started. Mint installation and Cinnamon login remain UNVERIFIED.'
)) {
   throw 'Creating a VM requires local ISO and independently authenticated SHA256'
 }
 if ($Unattended -and -not $Secret) { throw 'Protected password file required' }
}
if ($SelfTest) {
 Assert-Options $false $false $false '' '' ''
 $blocked = $false
 try { Assert-Options $false $false $true '' '' '' } catch { $blocked = $true }
 if (-not $blocked) { throw 'Start without installation was accepted' }
 Write-Output 'PASS: standalone bootstrap safety gates'
 exit 0
}
Assert-Options ([bool]$CreateVM) ([bool]$ConfigureUnattended) ([bool]$StartVM) $IsoPath $IsoSha256 $PasswordFile
$git = Get-Command git.exe -ErrorAction SilentlyContinue
if ($null -eq $git) { throw 'Git for Windows required: https://git-scm.com/downloads/win' }
$base = Join-Path $env:LOCALAPPDATA 'CanopyTestLab'
$checkout = Join-Path $base 'source'
if (-not (Test-Path -LiteralPath $checkout)) {
 New-Item -ItemType Directory -Path $base -Force | Out-Null
 & $git.Source clone '--depth=1' '--single-branch' '--branch' $branch $repository $checkout
 if ($LASTEXITCODE -ne 0) { throw 'Repository checkout failed' }
} else {
 if (-not (Test-Path -LiteralPath (Join-Path $checkout '.git'))) { throw 'Existing source path is not a Git checkout' }
 $origin = (& $git.Source -C $checkout remote get-url origin | Out-String).Trim()
 if ($LASTEXITCODE -ne 0 -or $origin -ne $repository) { throw 'Existing source checkout has unexpected origin; refusing to run' }
 $currentBranch = (& $git.Source -C $checkout branch '--show-current' | Out-String).Trim()
 if ($currentBranch -ne $branch) { throw 'Existing checkout is on unexpected branch' }
 $dirty = (& $git.Source -C $checkout status '--porcelain=v1' '--untracked-files=all' | Out-String).Trim()
 if ($LASTEXITCODE -ne 0 -or $dirty) { throw 'Existing source checkout is dirty; refusing to run' }
 & $git.Source -C $checkout pull '--ff-only'
 if ($LASTEXITCODE -ne 0) { throw 'Could not safely update checkout' }
}
$launcher = Join-Path $checkout 'scripts\Start-CanopyTestLab.ps1'
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) { throw 'Missing Canopy launcher' }
if (-not $CreateVM) {
 & $launcher
 if ($LASTEXITCODE -ne 0) { throw 'Host preflight blocked' }
 Write-Output 'Host ready. Mint ISO verification and VM creation not started.'
 exit 0
}
& $launcher -Provision -IsoPath $IsoPath -IsoSha256 $IsoSha256 -ConfigureUnattended:$ConfigureUnattended -PasswordFile $PasswordFile
if ($LASTEXITCODE -ne 0) { throw 'VM provisioning failed' }
if (-not $StartVM) { exit 0 }
$vbox = Join-Path $env:ProgramFiles 'Oracle\VirtualBox\VBoxManage.exe'
if (-not (Test-Path -LiteralPath $vbox -PathType Leaf)) { throw 'VirtualBox CLI missing' }
& $vbox startvm $vm '--type=headless'
if ($LASTEXITCODE -ne 0) { throw 'VM start failed; inspect guest state' }
Write-Output 'VM started. Mint installation and Cinnamon login remain UNVERIFIED.'
) { throw 'Independently authenticated SHA256 required before download' }
 $uri = $null
 if (-not [Uri]::TryCreate($Url,[UriKind]::Absolute,[ref]$uri) -or
     $uri.Scheme -ne 'https' -or $uri.UserInfo -or $uri.Fragment) {
   throw 'ISO URL must be a clean HTTPS address'
 }
 if (-not $uri.AbsolutePath.EndsWith('.iso',[StringComparison]::OrdinalIgnoreCase)) {
   throw 'Download URL must end in .iso'
 }
 $parent = Split-Path -Parent $Destination
 New-Item -ItemType Directory -Path $parent -Force | Out-Null
 if (Test-Path -LiteralPath $Destination -PathType Leaf) {
   if ((Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash -eq $ExpectedHash.ToUpperInvariant()) {
     Write-Output 'Reusing already verified ISO'
     return $Destination
   }
   throw 'Existing ISO checksum differs; refusing overwrite'
 }
 $temporary = Join-Path $parent ('mint-download-' + [guid]::NewGuid().ToString('N') + '.part')
 try {
   Write-Output 'Downloading Mint ISO over HTTPS; validating complete file SHA256 before use'
   Invoke-WebRequest -Uri $uri.AbsoluteUri -OutFile $temporary -MaximumRedirection 5 -ErrorAction Stop
   $actual = (Get-FileHash -LiteralPath $temporary -Algorithm SHA256).Hash
   if ($actual -ne $ExpectedHash.ToUpperInvariant()) { throw 'Downloaded ISO SHA256 mismatch; file rejected' }
   if (Test-Path -LiteralPath $Destination) { throw 'ISO destination appeared during download; refusing overwrite' }
   Move-Item -LiteralPath $temporary -Destination $Destination -ErrorAction Stop
   return $Destination
 } finally {
   if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
 }
}
function Assert-Options {
 param([bool]$Create,[bool]$Unattended,[bool]$Start,[string]$Iso,[string]$Hash,[string]$Secret)
 if ($Unattended -and -not $Create) { throw 'Unattended requires CreateVM' }
 if ($Start -and -not $Unattended) { throw 'StartVM requires unattended configuration in this run' }
 if ($Create -and (-not $Iso -or $Hash -notmatch '^[0-9a-fA-F]{64}$')) {
   throw 'Creating a VM requires local ISO and independently authenticated SHA256'
 }
 if ($Unattended -and -not $Secret) { throw 'Protected password file required' }
}
if ($SelfTest) {
 Assert-Options $false $false $false '' '' ''
 $blocked = $false
 try { Assert-Options $false $false $true '' '' '' } catch { $blocked = $true }
 if (-not $blocked) { throw 'Start without installation was accepted' }
 Write-Output 'PASS: standalone bootstrap safety gates'
 exit 0
}
Assert-Options ([bool]$CreateVM) ([bool]$ConfigureUnattended) ([bool]$StartVM) $IsoPath $IsoSha256 $PasswordFile
$git = Get-Command git.exe -ErrorAction SilentlyContinue
if ($null -eq $git) { throw 'Git for Windows required: https://git-scm.com/downloads/win' }
$base = Join-Path $env:LOCALAPPDATA 'CanopyTestLab'
$checkout = Join-Path $base 'source'
if (-not (Test-Path -LiteralPath $checkout)) {
 New-Item -ItemType Directory -Path $base -Force | Out-Null
 & $git.Source clone '--depth=1' '--single-branch' '--branch' $branch $repository $checkout
 if ($LASTEXITCODE -ne 0) { throw 'Repository checkout failed' }
} else {
 if (-not (Test-Path -LiteralPath (Join-Path $checkout '.git'))) { throw 'Existing source path is not a Git checkout' }
 $origin = (& $git.Source -C $checkout remote get-url origin | Out-String).Trim()
 if ($LASTEXITCODE -ne 0 -or $origin -ne $repository) { throw 'Existing source checkout has unexpected origin; refusing to run' }
 $currentBranch = (& $git.Source -C $checkout branch '--show-current' | Out-String).Trim()
 if ($currentBranch -ne $branch) { throw 'Existing checkout is on unexpected branch' }
 $dirty = (& $git.Source -C $checkout status '--porcelain=v1' '--untracked-files=all' | Out-String).Trim()
 if ($LASTEXITCODE -ne 0 -or $dirty) { throw 'Existing source checkout is dirty; refusing to run' }
 & $git.Source -C $checkout pull '--ff-only'
 if ($LASTEXITCODE -ne 0) { throw 'Could not safely update checkout' }
}
$launcher = Join-Path $checkout 'scripts\Start-CanopyTestLab.ps1'
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) { throw 'Missing Canopy launcher' }
if (-not $CreateVM) {
 & $launcher
 if ($LASTEXITCODE -ne 0) { throw 'Host preflight blocked' }
 Write-Output 'Host ready. Mint ISO verification and VM creation not started.'
 exit 0
}
& $launcher -Provision -IsoPath $IsoPath -IsoSha256 $IsoSha256 -ConfigureUnattended:$ConfigureUnattended -PasswordFile $PasswordFile
if ($LASTEXITCODE -ne 0) { throw 'VM provisioning failed' }
if (-not $StartVM) { exit 0 }
$vbox = Join-Path $env:ProgramFiles 'Oracle\VirtualBox\VBoxManage.exe'
if (-not (Test-Path -LiteralPath $vbox -PathType Leaf)) { throw 'VirtualBox CLI missing' }
& $vbox startvm $vm '--type=headless'
if ($LASTEXITCODE -ne 0) { throw 'VM start failed; inspect guest state' }
Write-Output 'VM started. Mint installation and Cinnamon login remain UNVERIFIED.'
