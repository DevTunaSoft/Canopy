#Requires -Version 5.1
<#
.SYNOPSIS
Register an explicitly authorized least-privilege task for approved Mint tests.
No task is created without -Enable; never runs as SYSTEM or with stored password.
#>
[CmdletBinding()]
param(
    [string]$RepoPath = '',
    [string]$ConfigPath = '',
    [switch]$Enable,
    [switch]$Disable,
    [switch]$SelfTest
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$taskName = 'CanopyTestLab-ApprovedTests'
function Get-CanopySchedulePlan {
    param([string]$Repository,[string]$Configuration)
    if (-not $Repository -or -not $Configuration) { throw 'Repository and configuration required' }
    return [pscustomobject]@{
        task_name = 'CanopyTestLab-ApprovedTests'
        interval_minutes = 30
        run_level = 'Limited'
        logon_type = 'Interactive'
        interactive_login_required = $true
        executable_module = 'scripts.testlab_host_supervisor'
        repository = $Repository
        configuration = $Configuration
        schedule_installed = $false
    }
}
if ($SelfTest) {
    $plan = Get-CanopySchedulePlan 'C:\CanopyTest\repo' 'C:\CanopyTest\host.json'
    if ($plan.task_name -ne $taskName -or $plan.interval_minutes -ne 30 -or
        $plan.run_level -ne 'Limited' -or -not $plan.interactive_login_required) {
        throw 'Scheduler plan validation failed'
    }
    Write-Output 'PASS: safe scheduled-task plan; no Windows changes'
    exit 0
}
if ($Enable -and $Disable) { throw 'Choose only -Enable or -Disable' }
if (-not $Enable -and -not $Disable) {
    Write-Output 'No scheduled task changes. Supply -Enable explicitly after VM trust setup.'
    exit 0
}
Import-Module ScheduledTasks -ErrorAction Stop
if ($Disable) {
    $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($null -ne $existing) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Output 'Dedicated Canopy task removed; no VM or reports deleted.'
    } else {
        Write-Output 'Canopy task is not installed.'
    }
    exit 0
}
if (-not $RepoPath -or -not $ConfigPath) {
    throw '-RepoPath and -ConfigPath are required for -Enable'
}
$repository = (Resolve-Path -LiteralPath $RepoPath -ErrorAction Stop).ProviderPath
$config = (Resolve-Path -LiteralPath $ConfigPath -ErrorAction Stop).ProviderPath
if (-not (Test-Path -LiteralPath (Join-Path $repository 'scripts\testlab_host_supervisor.py') -PathType Leaf)) {
    throw 'The complete approved host-supervisor checkout is required'
}
if ($repository.Contains('"') -or $config.Contains('"')) {
    throw 'Double quotes are not permitted in scheduled task paths'
}
if ($null -ne (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue)) {
    throw 'Dedicated task already exists; refusing to overwrite it'
}
$python = Get-Command python.exe -ErrorAction Stop
$exe = $python.Source
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    throw 'Python executable missing'
}
$plan = Get-CanopySchedulePlan $repository $config
$arguments = ('-B -m scripts.testlab_host_supervisor --config "' + $config + '"')
$action = New-ScheduledTaskAction -Execute $exe -Argument $arguments -WorkingDirectory $repository
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 30) `
    -RepetitionDuration (New-TimeSpan -Days 365)
$account = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $account -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
Register-ScheduledTask -TaskName $taskName -Description 'Isolated Canopy Mint approved tests only' `
    -Action $action -Trigger $trigger -Principal $principal -Settings $settings -ErrorAction Stop | Out-Null
Write-Output 'Canopy approved-test task registered for current logged-in Windows user.'
Write-Output 'The task does not run while signed out; no SYSTEM task or stored passwords are used.'
