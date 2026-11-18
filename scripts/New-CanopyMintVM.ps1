#Requires -Version 5.1
<#
.SYNOPSIS
Create ONLY a dedicated VirtualBox VM from a locally verified Mint ISO.
No real VM creation unless -Create is given. Never erases or reuses a VM.
#>
[CmdletBinding()]
param(
  [string]$IsoPath = '',
  [string]$IsoSha256 = '',
  [string]$VBoxManage = '',
  [string]$VmDirectory = '',
  [switch]$Create,
  [switch]$SelfTest
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
function Get-CanopyVBoxPlan {
    param([string]$VmName, [string]$DiskPath, [string]$IsoFile)
    if ($VmName -ne 'Canopy-Test-Mint') { throw 'Only dedicated Canopy VM is permitted' }
    if (-not $IsoFile -or -not $DiskPath) { throw 'ISO and disk paths required' }
    return @(
       @('createvm', '--name', $VmName, '--ostype', 'Ubuntu_64', '--register'),
       @('modifyvm', $VmName, '--memory', '4096', '--cpus', '2', '--vram', '128',
         '--graphicscontroller', 'vmsvga', '--nic1', 'nat', '--clipboard-mode', 'disabled',
         '--draganddrop', 'disabled'),
       @('modifyvm', $VmName, '--natpf1', 'canopy-ssh,tcp,127.0.0.1,2222,,22'),
       @('createmedium', 'disk', '--filename', $DiskPath, '--size', '40960', '--format', 'VDI'),
       @('storagectl', $VmName, '--name', 'SATA', '--add', 'sata', '--controller', 'IntelAhci'),
       @('storageattach', $VmName, '--storagectl', 'SATA', '--port', '0', '--device', '0',
          '--type', 'hdd', '--medium', $DiskPath),
       @('storageattach', $VmName, '--storagectl', 'SATA', '--port', '1', '--device', '0',
          '--type', 'dvddrive', '--medium', $IsoFile)
    )
}
if ($SelfTest) {
    $commands = @(Get-CanopyVBoxPlan 'Canopy-Test-Mint' 'X:\isolated\test.vdi' 'X:\mint.iso')
    if ($commands.Count -ne 7 -or $commands[1] -notcontains 'disabled' -or
        $commands[2] -notcontains 'canopy-ssh,tcp,127.0.0.1,2222,,22') {
        throw 'VirtualBox plan regression'
    }
    Write-Output 'PASS: verified only dedicated VM commands without executing VirtualBox'
    exit 0
}
if (-not $IsoPath -or $IsoSha256 -notmatch '^[0-9a-fA-F]{64}$') {
    throw 'Specify a local Mint ISO and independently verified 64-digit SHA256'
}
$iso = (Resolve-Path -LiteralPath $IsoPath -ErrorAction Stop).ProviderPath
if (-not $iso.EndsWith('.iso', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Input must be an ISO file'
}
$actual = (Get-FileHash -LiteralPath $iso -Algorithm SHA256).Hash
if ($actual -ne $IsoSha256.ToUpperInvariant()) {
    throw 'Mint ISO hash does not match the approved expected checksum'
}
if (-not $VBoxManage) {
    $VBoxManage = Join-Path $env:ProgramFiles 'Oracle\VirtualBox\VBoxManage.exe'
}
if (-not (Test-Path -LiteralPath $VBoxManage -PathType Leaf)) {
    throw 'Install official VirtualBox before creating the VM'
}
if (-not $VmDirectory) {
    $VmDirectory = Join-Path $env:LOCALAPPDATA 'CanopyTestLab\VirtualMachines'
}
$dir = [IO.Path]::GetFullPath($VmDirectory)
$disk = Join-Path $dir 'Canopy-Test-Mint.vdi'
if (Test-Path -LiteralPath $disk) { throw 'Dedicated disk path already exists; will not overwrite' }
$names = & $VBoxManage list vms
if ($LASTEXITCODE -ne 0) { throw 'Unable to enumerate VirtualBox VMs' }
if (($names | Out-String) -match '(?m)^"Canopy-Test-Mint"\s') {
    throw 'Dedicated VM already exists. No reconfiguration or overwrite permitted'
}
$plan = @(Get-CanopyVBoxPlan 'Canopy-Test-Mint' $disk $iso)
if (-not $Create) {
    Write-Output ('DRY RUN: ' + $plan.Count + ' bounded VirtualBox commands planned')
    Write-Output 'Specify -Create only after reviewing the VM name, ISO hash and isolated disk location'
    exit 0
}
New-Item -ItemType Directory -Path $dir -Force | Out-Null
foreach ($command in $plan) {
    & $VBoxManage @command | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw ('VirtualBox command failed: ' + $command[0] +
               '. Inspect dedicated VM and disk before retry; no automatic destructive cleanup')
    }
}
Write-Output 'Dedicated Mint VM hardware created and ISO attached. Mint OS is NOT YET INSTALLED.'
