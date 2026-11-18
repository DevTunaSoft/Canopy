#Requires -Version 5.1
<#
.SYNOPSIS
Read-only Windows host prerequisites for the future Canopy Mint VirtualBox lab.
No software installation, service modification, download, or VM launch.
#>
[CmdletBinding()]
param(
    [string]$OutputPath = '',
    [switch]$SelfTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Test-CanopyHostSnapshot {
    param([Parameter(Mandatory=$true)][psobject]$Snapshot)
    $checks = @(
        [pscustomobject]@{ Name='windows'; Pass=($Snapshot.Windows -eq $true); Detail='Windows host required' },
        [pscustomobject]@{ Name='memory'; Pass=($Snapshot.MemoryGiB -ge 8); Detail='At least 8 GiB installed RAM (4 GiB allocated to VM)' },
        [pscustomobject]@{ Name='cores'; Pass=($Snapshot.LogicalCores -ge 4); Detail='At least four logical processors preferred' },
        [pscustomobject]@{ Name='storage'; Pass=($Snapshot.FreeGiB -ge 60); Detail='At least 60 GiB free on selected system drive' },
        [pscustomobject]@{ Name='virtualbox'; Pass=($Snapshot.VirtualBox -eq $true); Detail='VirtualBox CLI detected; absence does not trigger installation' }
    )
    $state = if (@($checks | Where-Object { -not $_.Pass }).Count -eq 0) { 'PASS' } else { 'BLOCKED' }
    return [pscustomobject]@{
        schema_version = 1
        status = $state
        checks = @($checks | ForEach-Object {
            [pscustomobject]@{ name=$_.Name; status=$(if ($_.Pass) { 'PASS' } else { 'BLOCKED' }); detail=$_.Detail }
        })
        note = 'Host preflight only: no Linux Mint VM or VirtualBox tests were executed'
    }
}

function Get-CanopyHostSnapshot {
    $os = Get-CimInstance -ClassName Win32_OperatingSystem
    $cs = Get-CimInstance -ClassName Win32_ComputerSystem
    $diskId = $env:SystemDrive
    if ([string]::IsNullOrWhiteSpace($diskId)) { throw 'SystemDrive is unavailable' }
    $logicalDisk = Get-CimInstance -ClassName Win32_LogicalDisk -Filter ("DeviceID='" + $diskId.Replace("'","''") + "'")
    if ($null -eq $logicalDisk) { throw 'Cannot inspect system drive free space' }
    $vbox = Get-Command 'VBoxManage.exe' -ErrorAction SilentlyContinue
    if ($null -eq $vbox -and $env:ProgramFiles) {
        $candidate = Join-Path $env:ProgramFiles 'Oracle\VirtualBox\VBoxManage.exe'
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { $vbox = $candidate }
    }
    return [pscustomobject]@{
        Windows = ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT)
        MemoryGiB = [math]::Round([double]$cs.TotalPhysicalMemory / 1GB, 2)
        LogicalCores = [int]$cs.NumberOfLogicalProcessors
        FreeGiB = [math]::Round([double]$logicalDisk.FreeSpace / 1GB, 2)
        VirtualBox = ($null -ne $vbox)
    }
}

if ($SelfTest) {
    $good = [pscustomobject]@{Windows=$true;MemoryGiB=16;LogicalCores=8;FreeGiB=100;VirtualBox=$true}
    $result = Test-CanopyHostSnapshot $good
    if ($result.status -ne 'PASS' -or @($result.checks).Count -ne 5) { throw 'Expected PASS with five checks' }
    $bad = [pscustomobject]@{Windows=$true;MemoryGiB=4;LogicalCores=2;FreeGiB=5;VirtualBox=$false}
    $result = Test-CanopyHostSnapshot $bad
    if ($result.status -ne 'BLOCKED' -or @($result.checks | Where-Object status -eq 'BLOCKED').Count -ne 4) { throw 'Expected BLOCKED for insufficient host' }
    Write-Output 'PASS: host snapshot self-tests (ready and insufficient machine)'
    exit 0
}

$snapshot = Get-CanopyHostSnapshot
$report = Test-CanopyHostSnapshot $snapshot
$json = $report | ConvertTo-Json -Depth 6
if (-not [string]::IsNullOrWhiteSpace($OutputPath)) {
    $fullPath = [IO.Path]::GetFullPath($OutputPath)
    $directory = Split-Path -Parent $fullPath
    if (-not (Test-Path -LiteralPath $directory)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
    [IO.File]::WriteAllText($fullPath, $json + [Environment]::NewLine)
}
Write-Output $json
if ($report.status -ne 'PASS') { exit 1 }
