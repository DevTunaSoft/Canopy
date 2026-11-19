#Requires -Version 5.1
[CmdletBinding()]
param([ValidateSet('PASS','BLOCKED','FAIL')][string]$Status='BLOCKED',[string]$Stage='bootstrap',[switch]$SelfTest)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
function Assert-SafeField([string]$Value) { if ($Value -notmatch '^[a-zA-Z0-9_-]{1,48}$') { throw 'Unsafe status field' } }
function Get-CheckpointTitle([string]$Step) {
 Assert-SafeField $Step
 return ('Canopy checkpoint: ' + $Step)
}
function Select-CheckpointIssue([object[]]$Issues,[string]$Step) {
 $title=Get-CheckpointTitle $Step
 $matches=@($Issues | Where-Object { $_.title -ceq $title })
 if ($matches.Count -gt 1) { throw 'Multiple matching checkpoint issues; refusing ambiguous update' }
 if ($matches.Count -eq 0) { return 0 }
 $number=0
 if (-not [int]::TryParse([string]$matches[0].number,[ref]$number) -or $number -le 0) { throw 'Invalid checkpoint issue number' }
 return $number
}
function New-StatusBody([string]$State,[string]$Step) {
 Assert-SafeField $State; Assert-SafeField $Step
 return ('Canopy Windows launcher checkpoint' + [Environment]::NewLine + 'Status: ' + $State + [Environment]::NewLine + 'Stage: ' + $Step + [Environment]::NewLine + 'No host paths, logs, or credentials included.')
}
if ($SelfTest) {
 $body=New-StatusBody 'BLOCKED' 'wsl'
 if ($body -notmatch 'Status: BLOCKED') { throw 'Formatting regression' }
 $blocked=$false
 try { New-StatusBody 'FAIL' 'C:\Users\private' | Out-Null } catch { $blocked=$true }
 if (-not $blocked) { throw 'Private path accepted' }
 if ((Select-CheckpointIssue @([pscustomobject]@{title='Canopy checkpoint: wsl';number=42}) 'wsl') -ne 42) { throw 'Issue reuse regression' }
 if ((Select-CheckpointIssue @() 'wsl') -ne 0) { throw 'New checkpoint decision regression' }
 $ambiguous=$false
 try { Select-CheckpointIssue @([pscustomobject]@{title='Canopy checkpoint: wsl';number=42},[pscustomobject]@{title='Canopy checkpoint: wsl';number=43}) 'wsl' | Out-Null } catch { $ambiguous=$true }
 if (-not $ambiguous) { throw 'Duplicate issue ambiguity accepted' }
 'PASS: sanitized GitHub status and checkpoint issue reuse self-test'; exit 0
}
Assert-SafeField $Stage
if (-not (Get-Command gh.exe -ErrorAction SilentlyContinue)) { Write-Warning 'GitHub CLI unavailable; local log retained'; exit 0 }
& gh.exe auth status --hostname github.com 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Warning 'GitHub not authenticated; local log retained'; exit 0 }
$body=New-StatusBody $Status $Stage
$repo='DevTunaSoft/Canopy'
$raw=@(& gh.exe issue list --repo $repo --state open --limit 100 --json number,title)
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect existing checkpoint issues; refusing duplicate creation' }
$issues=@($raw | Out-String | ConvertFrom-Json)
$number=Select-CheckpointIssue $issues $Stage
if ($number -gt 0) {
 & gh.exe issue edit $number --repo $repo --body $body
} else {
 & gh.exe issue create --repo $repo --title (Get-CheckpointTitle $Stage) --body $body
}
if ($LASTEXITCODE -ne 0) { throw 'GitHub status publication failed' }
