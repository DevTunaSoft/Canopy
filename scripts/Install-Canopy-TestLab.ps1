#Requires -Version 5.1
<#
.SYNOPSIS
Safe one-command bootstrap PREPARATION for the future Canopy Linux Mint lab.
Never silently downloads ISOs, installs software, starts VMs, or changes the host.
#>
[CmdletBinding()]
param(
    [string]$Destination = '',
    [switch]$SelfTest
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
function New-CanopyBootstrapPlan {
    param([psobject]$HostEvidence)
    $preflight = $HostEvidence.status
    if ($preflight -notin @('PASS','BLOCKED')) { throw 'Unexpected prerequisite status' }
    $plan = [ordered]@{
        schema_version = 1
        vm_name = 'Canopy-Test-Mint'
        snapshot = 'Canopy-Clean'
        provisioning_status = 'NOT_RUN'
        host_preflight = $preflight
        actions = @(
            [ordered]@{ id='virtualbox'; state='NOT_RUN'; description='Install VirtualBox from official verified distribution after separate authorization' }
            [ordered]@{ id='mint-iso'; state='NOT_RUN'; description='Acquire and verify the chosen Linux Mint Cinnamon ISO and exact release checksum/signature' }
            [ordered]@{ id='unattended-install'; state='NOT_RUN'; description='Create isolated VM and perform Mint unattended installation after installer support is verified' }
            [ordered]@{ id='snapshot'; state='NOT_RUN'; description='Create and inspect a clean named snapshot before testing' }
            [ordered]@{ id='trusted-worker'; state='NOT_RUN'; description='Install approved-job-only worker and independent host evidence collector' }
        )
        limitations = 'Preparation only; actual VM creation and autonomous testing are NOT IMPLEMENTED'
    }
    return $plan
}
if ($SelfTest) {
    $good = New-CanopyBootstrapPlan ([pscustomobject]@{status='PASS'})
    $blocked = New-CanopyBootstrapPlan ([pscustomobject]@{status='BLOCKED'})
    if ($good.vm_name -ne 'Canopy-Test-Mint' -or $blocked.host_preflight -ne 'BLOCKED' -or
        $good.actions.Count -ne 5 -or @($good.actions | Where-Object state -ne 'NOT_RUN').Count -ne 0) {
        throw 'Bootstrap plan self-test failed'
    }
    Write-Output 'PASS: bootstrap preparation self-test'
    exit 0
}
if ([string]::IsNullOrWhiteSpace($Destination)) {
    $Destination = Join-Path $env:LOCALAPPDATA 'CanopyTestLab'
}
$target = [IO.Path]::GetFullPath($Destination)
$probe = Join-Path $PSScriptRoot 'Test-CanopyHost.ps1'
if (-not (Test-Path -LiteralPath $probe -PathType Leaf)) {
    throw 'Missing Windows host preflight script; use the complete repo with PR #27 integrated'
}
$lines = & $probe 2>&1
$exitCode = $LASTEXITCODE
if ($exitCode -notin @(0,1)) { throw 'Windows host preflight could not execute' }
$hostEvidence = (($lines | Out-String).Trim() | ConvertFrom-Json)
$plan = New-CanopyBootstrapPlan $hostEvidence
New-Item -ItemType Directory -Path $target -Force | Out-Null
$hostPath = Join-Path $target 'host-preflight.json'
$planPath = Join-Path $target 'bootstrap-plan.json'
[IO.File]::WriteAllText($hostPath, ($hostEvidence | ConvertTo-Json -Depth 10) + [Environment]::NewLine)
[IO.File]::WriteAllText($planPath, ($plan | ConvertTo-Json -Depth 10) + [Environment]::NewLine)
Write-Output ('Canopy Test Lab preparation: ' + $plan.host_preflight)
Write-Output ('Readiness details: ' + $hostPath)
Write-Output ('Provisioning plan: ' + $planPath)
Write-Output 'No software installed, VMs created or tests executed.'
if ($plan.host_preflight -ne 'PASS') { exit 1 }
