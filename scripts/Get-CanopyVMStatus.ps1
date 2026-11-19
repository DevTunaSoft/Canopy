#Requires -Version 5.1
<#
.SYNOPSIS
Read-only Windows VirtualBox inspection for the dedicated Canopy Mint VM.
Never starts, resets, removes, snapshots or modifies any VM.
#>
[CmdletBinding()]
param(
  [string]$VBoxManage = '',
  [string]$Destination = '',
  [switch]$SelfTest
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
function ConvertFrom-CanopyVmInfo {
  param([string[]]$Lines)
  $values = @{}
  foreach ($line in $Lines) {
    if ($line -match '^([A-Za-z][A-Za-z0-9_-]*)="([^"]*)"$') {
      $values[$Matches[1]] = $Matches[2]
    }
  }
  if ($values['name'] -ne 'Canopy-Test-Mint') { throw 'Unexpected VM identity' }
  if ($values['VMState'] -notin @('poweroff','running','saved','aborted','paused')) {
    throw 'Unexpected or missing VM state'
  }
  if ($values['UUID'] -notmatch '^[0-9a-fA-F-]{36}$') { throw 'Missing valid VM UUID' }
  return [ordered]@{
    schema_version=1
    vm_name='Canopy-Test-Mint'
    vm_uuid=$values['UUID']
    vm_state=$values['VMState']
    boot_verified=$false
    mint_installed='NOT_VERIFIED'
    cinnamon_tested='NOT_RUN'
    guest_ssh='NOT_VERIFIED'
  }
}
if ($SelfTest) {
  $sample = @('name="Canopy-Test-Mint"',
    'UUID="12345678-1234-1234-1234-123456789abc"','VMState="poweroff"')
  $result = ConvertFrom-CanopyVmInfo $sample
  if ($result.vm_state -ne 'poweroff' -or $result.boot_verified -ne $false) {
    throw 'VM inspection contract failed'
  }
  try {
    ConvertFrom-CanopyVmInfo @('name="Personal-VM"','VMState="running"')
    throw 'Unexpected VM was accepted'
  } catch {
    if ($_.Exception.Message -eq 'Unexpected VM was accepted') { throw }
  }
  Write-Output 'PASS: read-only VM identity and state inspection'
  exit 0
}
if (-not $VBoxManage) { $VBoxManage = Join-Path $env:ProgramFiles 'Oracle\VirtualBox\VBoxManage.exe' }
if (-not (Test-Path -LiteralPath $VBoxManage -PathType Leaf)) {
  throw 'VirtualBox missing; no VM inspected'
}
$lines = & $VBoxManage showvminfo 'Canopy-Test-Mint' '--machinereadable'
if ($LASTEXITCODE -ne 0) { throw 'Dedicated Canopy VM does not exist or is inaccessible' }
$report = ConvertFrom-CanopyVmInfo $lines
if (-not $Destination) { $Destination = Join-Path $env:LOCALAPPDATA 'CanopyTestLab\vm-inspection.json' }
$target = [IO.Path]::GetFullPath($Destination)
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
[IO.File]::WriteAllText($target, ($report | ConvertTo-Json -Depth 4) + [Environment]::NewLine)
Write-Output ('Read-only VM inspection saved: ' + $target)
Write-Output ('VM state: ' + $report.vm_state)
Write-Output 'Mint boot, Cinnamon login and SSH remain NOT VERIFIED.'
