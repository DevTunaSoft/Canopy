#Requires -Version 5.1
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$IsoPath,
  [Parameter(Mandatory=$true)][string]$IsoSha256,
  [switch]$SelfTest
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
function Assert-ResumeInputs {
  param([string]$Iso, [string]$Hash)
  if (-not $Iso -or $Hash -notmatch '^[a-fA-F0-9]{64}$') { throw 'ISO path and authenticated SHA256 required' }
}
if ($SelfTest) {
  $rejected = $false
  try { Assert-ResumeInputs '' 'invalid' } catch { $rejected = $true }
  if (-not $rejected) { throw 'Unsafe resume input accepted' }
  Assert-ResumeInputs 'C:\mint.iso' ('a' * 64)
  Write-Output 'PASS: resume argument safety'
  exit 0
}
Assert-ResumeInputs $IsoPath $IsoSha256
$iso = (Resolve-Path -LiteralPath $IsoPath -ErrorAction Stop).ProviderPath
if ((Get-FileHash -LiteralPath $iso -Algorithm SHA256).Hash -ne $IsoSha256.ToUpperInvariant()) {
  throw 'ISO SHA256 mismatch'
}
$vbox = Join-Path $env:ProgramFiles 'Oracle\VirtualBox\VBoxManage.exe'
if (-not (Test-Path -LiteralPath $vbox -PathType Leaf)) { throw 'VirtualBox not found' }
$info = & $vbox showvminfo 'Canopy-Test-Mint' '--machinereadable'
if ($LASTEXITCODE -ne 0 -or ($info | Out-String) -notmatch '(?m)^VMState="poweroff"\s*$') {
  throw 'Existing Canopy-Test-Mint VM must be powered off'
}
$secretDir = Join-Path $env:LOCALAPPDATA 'CanopyTestLab\secrets'
New-Item -ItemType Directory -Path $secretDir -Force | Out-Null
$secretFile = Join-Path $secretDir ('mint-' + [guid]::NewGuid().ToString('N') + '.txt')
$pointer = [IntPtr]::Zero
$password = $null
try {
  $secure = Read-Host 'Choose a password for the Linux test account (8-64 ASCII characters)' -AsSecureString
  $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
  $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
  if ($password -cnotmatch '^[\x21-\x7e]{8,64}$') { throw 'Password must be 8-64 printable ASCII characters without spaces' }
  [IO.File]::WriteAllText($secretFile, $password, (New-Object Text.UTF8Encoding($false)))
  $acl = Get-Acl -LiteralPath $secretFile
  $acl.SetAccessRuleProtection($true, $false)
  $rule = [Security.AccessControl.FileSystemAccessRule]::new(
    [Security.Principal.WindowsIdentity]::GetCurrent().User,
    [Security.AccessControl.FileSystemRights]::FullControl,
    [Security.AccessControl.AccessControlType]::Allow)
  $acl.AddAccessRule($rule)
  Set-Acl -LiteralPath $secretFile -AclObject $acl
  $installer = Join-Path $PSScriptRoot 'Install-CanopyMintOS.ps1'
  $auxDir = Join-Path $env:LOCALAPPDATA 'CanopyTestLab\unattended-media'
  New-Item -ItemType Directory -Path $auxDir -Force | Out-Null
  $auxPath = Join-Path $auxDir ('CanopyMint-' + [guid]::NewGuid().ToString('N'))
  & $installer -IsoPath $iso -IsoSha256 $IsoSha256 -PasswordFile $secretFile -AuxiliaryBasePath $auxPath
  if ($LASTEXITCODE -ne 0) { throw 'VirtualBox unattended dry-run failed' }
  & $installer -IsoPath $iso -IsoSha256 $IsoSha256 -PasswordFile $secretFile -AuxiliaryBasePath $auxPath -Install
  if ($LASTEXITCODE -ne 0) { throw 'VirtualBox unattended configuration failed' }
} finally {
  $password = $null
  if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
  if (Test-Path -LiteralPath $secretFile -PathType Leaf) { Remove-Item -LiteralPath $secretFile -Force }
}
& $vbox startvm 'Canopy-Test-Mint' '--type=gui'
if ($LASTEXITCODE -ne 0) { throw 'VM start failed' }
Write-Output 'Mint installation started; actual installation and desktop boot remain unverified.'
