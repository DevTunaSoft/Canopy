#Requires -Version 5.1
<#
.SYNOPSIS
Canopy Windows VM test-lab entry point. No VM changes unless -CreateVM.
The ISO checksum must be authenticated independently.
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
    [switch]$ResumeExistingVM,
    [switch]$SelfTest
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-Options {
    param([bool]$Create, [bool]$Unattended, [bool]$Start, [string]$Iso,
          [string]$Hash, [string]$Secret, [string]$Url)
    if ($Unattended -and -not $Create) { throw 'ConfigureUnattended requires CreateVM' }
    if ($Start -and -not $Unattended) { throw 'StartVM requires ConfigureUnattended' }
    if ($Iso -and $Url) { throw 'Specify either IsoPath or IsoUrl, not both' }
    if ($Create -and ((-not $Iso -and -not $Url) -or $Hash -notmatch '^[0-9a-fA-F]{64}$')) {
        throw 'VM creation requires an ISO path or URL and an independently authenticated SHA256'
    }
    if ($Unattended -and -not $Secret) { throw 'A protected password file is required' }
}

function Invoke-ExistingVmInstall {
    param([string]$Iso, [string]$Hash, [string]$Base)
    if (-not $Iso -or $Hash -notmatch '^[0-9a-fA-F]{64}
    param([string]$Url, [string]$ExpectedHash, [string]$Destination)
    $uri = $null
    if (-not [Uri]::TryCreate($Url, [UriKind]::Absolute, [ref]$uri) -or
        $uri.Scheme -ne 'https' -or $uri.UserInfo -or $uri.Fragment -or
        -not $uri.AbsolutePath.EndsWith('.iso', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'ISO URL must be a direct HTTPS .iso URL without credentials or fragments'
    }
    $parent = Split-Path -Parent $Destination
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    if (Test-Path -LiteralPath $Destination -PathType Leaf) {
        if ((Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash -eq $ExpectedHash.ToUpperInvariant()) {
            return $Destination
        }
        throw 'Existing ISO has an unexpected checksum; refusing to overwrite'
    }
    $temporary = Join-Path $parent ('download-' + [guid]::NewGuid().ToString('N') + '.part')
    try {
        Invoke-WebRequest -Uri $uri.AbsoluteUri -OutFile $temporary -MaximumRedirection 5 -ErrorAction Stop
        $actual = (Get-FileHash -LiteralPath $temporary -Algorithm SHA256).Hash
        if ($actual -ne $ExpectedHash.ToUpperInvariant()) { throw 'ISO SHA256 mismatch; download rejected' }
        if (Test-Path -LiteralPath $Destination) { throw 'ISO destination already exists; refusing overwrite' }
        Move-Item -LiteralPath $temporary -Destination $Destination -ErrorAction Stop
        return $Destination
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
    }
}

if ($SelfTest) {
    Assert-Options $false $false $false '' '' '' ''
    $rejected = $false
    try { Assert-Options $false $false $true '' '' '' '' } catch { $rejected = $true }
    if (-not $rejected) { throw 'Safety test failed: StartVM without authorization' }
    $rejected = $false
    try { Assert-Options $true $false $false '' 'invalid' '' 'https://example.org/mint.iso' } catch { $rejected = $true }
    if (-not $rejected) { throw 'Safety test failed: unverified ISO accepted' }
    Write-Output 'PASS: Canopy setup option safety tests'
    exit 0
}

if ($ResumeExistingVM -and ($CreateVM -or $ConfigureUnattended -or $StartVM -or $IsoUrl)) {
    throw 'ResumeExistingVM must not be combined with creation or download switches'
}
if (-not $ResumeExistingVM) {
    Assert-Options ([bool]$CreateVM) ([bool]$ConfigureUnattended) ([bool]$StartVM) $IsoPath $IsoSha256 $PasswordFile $IsoUrl
}
$git = Get-Command 'git.exe' -ErrorAction SilentlyContinue
if ($null -eq $git) { throw 'Git for Windows is required' }
$repository = 'https://github.com/DevTunaSoft/Canopy.git'
$branch = 'fix/testlab-replay-proof-transport'
$base = Join-Path $env:LOCALAPPDATA 'CanopyTestLab'
$checkout = Join-Path $base 'source'
if (-not (Test-Path -LiteralPath $checkout)) {
    New-Item -ItemType Directory -Path $base -Force | Out-Null
    & $git.Source clone '--depth=1' '--single-branch' '--branch' $branch $repository $checkout
    if ($LASTEXITCODE -ne 0) { throw 'Git clone failed' }
} else {
    if (-not (Test-Path -LiteralPath (Join-Path $checkout '.git'))) { throw 'Source folder is not a Git checkout' }
    $origin = (& $git.Source -C $checkout remote get-url origin | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $origin -ne $repository) { throw 'Unexpected Git origin' }
    $currentBranch = (& $git.Source -C $checkout branch '--show-current' | Out-String).Trim()
    if ($currentBranch -ne $branch) { throw 'Unexpected Git branch' }
    $dirty = (& $git.Source -C $checkout status '--porcelain=v1' '--untracked-files=all' | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $dirty) { throw 'Checkout contains local modifications; refusing to overwrite' }
    & $git.Source -C $checkout pull '--ff-only'
    if ($LASTEXITCODE -ne 0) { throw 'Git fast-forward failed' }
}
if ($ResumeExistingVM) {
    Invoke-ExistingVmInstall -Iso $IsoPath -Hash $IsoSha256 -Base $base
    exit 0
}
$launcher = Join-Path $checkout 'scripts\Start-CanopyTestLab.ps1'
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) { throw 'Missing test-lab launcher' }
if (-not $CreateVM) {
    & $launcher
    if ($LASTEXITCODE -ne 0) { throw 'Host readiness checks failed' }
    Write-Output 'Host readiness complete; no VM changes requested'
    exit 0
}
if ($IsoUrl) {
    $IsoPath = Get-VerifiedMintIso -Url $IsoUrl -ExpectedHash $IsoSha256 -Destination (Join-Path $base 'downloads\linuxmint-canopy.iso')
}
& $launcher -Provision -IsoPath $IsoPath -IsoSha256 $IsoSha256 -ConfigureUnattended:$ConfigureUnattended -PasswordFile $PasswordFile
if ($LASTEXITCODE -ne 0) { throw 'VM provisioning failed' }
if (-not $StartVM) { exit 0 }
$vbox = Join-Path $env:ProgramFiles 'Oracle\VirtualBox\VBoxManage.exe'
if (-not (Test-Path -LiteralPath $vbox -PathType Leaf)) { throw 'VirtualBox CLI not found' }
& $vbox startvm 'Canopy-Test-Mint' '--type=headless'
if ($LASTEXITCODE -ne 0) { throw 'VM start failed' }
Write-Output 'VM started; Mint installation and Cinnamon login are not yet verified'
) {
        throw 'Resume requires the local ISO path and verified SHA256'
    }
    $isoFile = (Resolve-Path -LiteralPath $Iso -ErrorAction Stop).ProviderPath
    if ((Get-FileHash -LiteralPath $isoFile -Algorithm SHA256).Hash -ne $Hash.ToUpperInvariant()) {
        throw 'ISO checksum mismatch; refusing installation'
    }
    $vbox = Join-Path $env:ProgramFiles 'Oracle\VirtualBox\VBoxManage.exe'
    if (-not (Test-Path -LiteralPath $vbox -PathType Leaf)) { throw 'VirtualBox CLI missing' }
    $info = & $vbox showvminfo 'Canopy-Test-Mint' '--machinereadable'
    if ($LASTEXITCODE -ne 0 -or ($info | Out-String) -notmatch '(?m)^VMState="poweroff"\s*
    param([string]$Url, [string]$ExpectedHash, [string]$Destination)
    $uri = $null
    if (-not [Uri]::TryCreate($Url, [UriKind]::Absolute, [ref]$uri) -or
        $uri.Scheme -ne 'https' -or $uri.UserInfo -or $uri.Fragment -or
        -not $uri.AbsolutePath.EndsWith('.iso', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'ISO URL must be a direct HTTPS .iso URL without credentials or fragments'
    }
    $parent = Split-Path -Parent $Destination
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    if (Test-Path -LiteralPath $Destination -PathType Leaf) {
        if ((Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash -eq $ExpectedHash.ToUpperInvariant()) {
            return $Destination
        }
        throw 'Existing ISO has an unexpected checksum; refusing to overwrite'
    }
    $temporary = Join-Path $parent ('download-' + [guid]::NewGuid().ToString('N') + '.part')
    try {
        Invoke-WebRequest -Uri $uri.AbsoluteUri -OutFile $temporary -MaximumRedirection 5 -ErrorAction Stop
        $actual = (Get-FileHash -LiteralPath $temporary -Algorithm SHA256).Hash
        if ($actual -ne $ExpectedHash.ToUpperInvariant()) { throw 'ISO SHA256 mismatch; download rejected' }
        if (Test-Path -LiteralPath $Destination) { throw 'ISO destination already exists; refusing overwrite' }
        Move-Item -LiteralPath $temporary -Destination $Destination -ErrorAction Stop
        return $Destination
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
    }
}

if ($SelfTest) {
    Assert-Options $false $false $false '' '' '' ''
    $rejected = $false
    try { Assert-Options $false $false $true '' '' '' '' } catch { $rejected = $true }
    if (-not $rejected) { throw 'Safety test failed: StartVM without authorization' }
    $rejected = $false
    try { Assert-Options $true $false $false '' 'invalid' '' 'https://example.org/mint.iso' } catch { $rejected = $true }
    if (-not $rejected) { throw 'Safety test failed: unverified ISO accepted' }
    Write-Output 'PASS: Canopy setup option safety tests'
    exit 0
}

Assert-Options ([bool]$CreateVM) ([bool]$ConfigureUnattended) ([bool]$StartVM) $IsoPath $IsoSha256 $PasswordFile $IsoUrl
$git = Get-Command 'git.exe' -ErrorAction SilentlyContinue
if ($null -eq $git) { throw 'Git for Windows is required' }
$repository = 'https://github.com/DevTunaSoft/Canopy.git'
$branch = 'fix/testlab-replay-proof-transport'
$base = Join-Path $env:LOCALAPPDATA 'CanopyTestLab'
$checkout = Join-Path $base 'source'
if (-not (Test-Path -LiteralPath $checkout)) {
    New-Item -ItemType Directory -Path $base -Force | Out-Null
    & $git.Source clone '--depth=1' '--single-branch' '--branch' $branch $repository $checkout
    if ($LASTEXITCODE -ne 0) { throw 'Git clone failed' }
} else {
    if (-not (Test-Path -LiteralPath (Join-Path $checkout '.git'))) { throw 'Source folder is not a Git checkout' }
    $origin = (& $git.Source -C $checkout remote get-url origin | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $origin -ne $repository) { throw 'Unexpected Git origin' }
    $currentBranch = (& $git.Source -C $checkout branch '--show-current' | Out-String).Trim()
    if ($currentBranch -ne $branch) { throw 'Unexpected Git branch' }
    $dirty = (& $git.Source -C $checkout status '--porcelain=v1' '--untracked-files=all' | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $dirty) { throw 'Checkout contains local modifications; refusing to overwrite' }
    & $git.Source -C $checkout pull '--ff-only'
    if ($LASTEXITCODE -ne 0) { throw 'Git fast-forward failed' }
}
$launcher = Join-Path $checkout 'scripts\Start-CanopyTestLab.ps1'
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) { throw 'Missing test-lab launcher' }
if (-not $CreateVM) {
    & $launcher
    if ($LASTEXITCODE -ne 0) { throw 'Host readiness checks failed' }
    Write-Output 'Host readiness complete; no VM changes requested'
    exit 0
}
if ($IsoUrl) {
    $IsoPath = Get-VerifiedMintIso -Url $IsoUrl -ExpectedHash $IsoSha256 -Destination (Join-Path $base 'downloads\linuxmint-canopy.iso')
}
& $launcher -Provision -IsoPath $IsoPath -IsoSha256 $IsoSha256 -ConfigureUnattended:$ConfigureUnattended -PasswordFile $PasswordFile
if ($LASTEXITCODE -ne 0) { throw 'VM provisioning failed' }
if (-not $StartVM) { exit 0 }
$vbox = Join-Path $env:ProgramFiles 'Oracle\VirtualBox\VBoxManage.exe'
if (-not (Test-Path -LiteralPath $vbox -PathType Leaf)) { throw 'VirtualBox CLI not found' }
& $vbox startvm 'Canopy-Test-Mint' '--type=headless'
if ($LASTEXITCODE -ne 0) { throw 'VM start failed' }
Write-Output 'VM started; Mint installation and Cinnamon login are not yet verified'
) {
        throw 'Dedicated Canopy-Test-Mint VM must exist and be powered off'
    }
    $secretDir = Join-Path $Base 'secrets'
    New-Item -ItemType Directory -Path $secretDir -Force | Out-Null
    $secretFile = Join-Path $secretDir ('mint-' + [guid]::NewGuid().ToString('N') + '.txt')
    $password = $null
    $ptr = [IntPtr]::Zero
    try {
        $secure = Read-Host 'Choose a password for the temporary Linux test account' -AsSecureString
        $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
        if ($password.Length -lt 8 -or $password.Length -gt 64 -or $password.Contains([char]10) -or $password.Contains([char]13)) {
            throw 'Use a password of 8-64 characters without line breaks'
        }
        [IO.File]::WriteAllText($secretFile, $password, [Text.UTF8Encoding]::new($false))
        $acl = Get-Acl -LiteralPath $secretFile
        $acl.SetAccessRuleProtection($true, $false)
        $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
            [Security.Principal.WindowsIdentity]::GetCurrent().User,
            [Security.AccessControl.FileSystemRights]::FullControl,
            [Security.AccessControl.AccessControlType]::Allow)
        $acl.AddAccessRule($rule)
        Set-Acl -LiteralPath $secretFile -AclObject $acl
        $installer = Join-Path $PSScriptRoot 'scripts\Install-CanopyMintOS.ps1'
        & $installer -IsoPath $isoFile -IsoSha256 $Hash -PasswordFile $secretFile
        if ($LASTEXITCODE -ne 0) { throw 'Unattended dry-run failed; VM unchanged' }
        & $installer -IsoPath $isoFile -IsoSha256 $Hash -PasswordFile $secretFile -Install
        if ($LASTEXITCODE -ne 0) { throw 'Unattended configuration failed; VM not started' }
        & $vbox startvm 'Canopy-Test-Mint' '--type=gui'
        if ($LASTEXITCODE -ne 0) { throw 'VM start failed' }
        Write-Output 'VM started. Mint installation is in progress; completion is NOT VERIFIED.'
    } finally {
        if ($ptr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
        $password = $null
        if (Test-Path -LiteralPath $secretFile -PathType Leaf) {
            Remove-Item -LiteralPath $secretFile -Force
        }
    }
}
function Get-VerifiedMintIso {
    param([string]$Url, [string]$ExpectedHash, [string]$Destination)
    $uri = $null
    if (-not [Uri]::TryCreate($Url, [UriKind]::Absolute, [ref]$uri) -or
        $uri.Scheme -ne 'https' -or $uri.UserInfo -or $uri.Fragment -or
        -not $uri.AbsolutePath.EndsWith('.iso', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'ISO URL must be a direct HTTPS .iso URL without credentials or fragments'
    }
    $parent = Split-Path -Parent $Destination
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    if (Test-Path -LiteralPath $Destination -PathType Leaf) {
        if ((Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash -eq $ExpectedHash.ToUpperInvariant()) {
            return $Destination
        }
        throw 'Existing ISO has an unexpected checksum; refusing to overwrite'
    }
    $temporary = Join-Path $parent ('download-' + [guid]::NewGuid().ToString('N') + '.part')
    try {
        Invoke-WebRequest -Uri $uri.AbsoluteUri -OutFile $temporary -MaximumRedirection 5 -ErrorAction Stop
        $actual = (Get-FileHash -LiteralPath $temporary -Algorithm SHA256).Hash
        if ($actual -ne $ExpectedHash.ToUpperInvariant()) { throw 'ISO SHA256 mismatch; download rejected' }
        if (Test-Path -LiteralPath $Destination) { throw 'ISO destination already exists; refusing overwrite' }
        Move-Item -LiteralPath $temporary -Destination $Destination -ErrorAction Stop
        return $Destination
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
    }
}

if ($SelfTest) {
    Assert-Options $false $false $false '' '' '' ''
    $rejected = $false
    try { Assert-Options $false $false $true '' '' '' '' } catch { $rejected = $true }
    if (-not $rejected) { throw 'Safety test failed: StartVM without authorization' }
    $rejected = $false
    try { Assert-Options $true $false $false '' 'invalid' '' 'https://example.org/mint.iso' } catch { $rejected = $true }
    if (-not $rejected) { throw 'Safety test failed: unverified ISO accepted' }
    Write-Output 'PASS: Canopy setup option safety tests'
    exit 0
}

Assert-Options ([bool]$CreateVM) ([bool]$ConfigureUnattended) ([bool]$StartVM) $IsoPath $IsoSha256 $PasswordFile $IsoUrl
$git = Get-Command 'git.exe' -ErrorAction SilentlyContinue
if ($null -eq $git) { throw 'Git for Windows is required' }
$repository = 'https://github.com/DevTunaSoft/Canopy.git'
$branch = 'fix/testlab-replay-proof-transport'
$base = Join-Path $env:LOCALAPPDATA 'CanopyTestLab'
$checkout = Join-Path $base 'source'
if (-not (Test-Path -LiteralPath $checkout)) {
    New-Item -ItemType Directory -Path $base -Force | Out-Null
    & $git.Source clone '--depth=1' '--single-branch' '--branch' $branch $repository $checkout
    if ($LASTEXITCODE -ne 0) { throw 'Git clone failed' }
} else {
    if (-not (Test-Path -LiteralPath (Join-Path $checkout '.git'))) { throw 'Source folder is not a Git checkout' }
    $origin = (& $git.Source -C $checkout remote get-url origin | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $origin -ne $repository) { throw 'Unexpected Git origin' }
    $currentBranch = (& $git.Source -C $checkout branch '--show-current' | Out-String).Trim()
    if ($currentBranch -ne $branch) { throw 'Unexpected Git branch' }
    $dirty = (& $git.Source -C $checkout status '--porcelain=v1' '--untracked-files=all' | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $dirty) { throw 'Checkout contains local modifications; refusing to overwrite' }
    & $git.Source -C $checkout pull '--ff-only'
    if ($LASTEXITCODE -ne 0) { throw 'Git fast-forward failed' }
}
$launcher = Join-Path $checkout 'scripts\Start-CanopyTestLab.ps1'
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) { throw 'Missing test-lab launcher' }
if (-not $CreateVM) {
    & $launcher
    if ($LASTEXITCODE -ne 0) { throw 'Host readiness checks failed' }
    Write-Output 'Host readiness complete; no VM changes requested'
    exit 0
}
if ($IsoUrl) {
    $IsoPath = Get-VerifiedMintIso -Url $IsoUrl -ExpectedHash $IsoSha256 -Destination (Join-Path $base 'downloads\linuxmint-canopy.iso')
}
& $launcher -Provision -IsoPath $IsoPath -IsoSha256 $IsoSha256 -ConfigureUnattended:$ConfigureUnattended -PasswordFile $PasswordFile
if ($LASTEXITCODE -ne 0) { throw 'VM provisioning failed' }
if (-not $StartVM) { exit 0 }
$vbox = Join-Path $env:ProgramFiles 'Oracle\VirtualBox\VBoxManage.exe'
if (-not (Test-Path -LiteralPath $vbox -PathType Leaf)) { throw 'VirtualBox CLI not found' }
& $vbox startvm 'Canopy-Test-Mint' '--type=headless'
if ($LASTEXITCODE -ne 0) { throw 'VM start failed' }
Write-Output 'VM started; Mint installation and Cinnamon login are not yet verified'
