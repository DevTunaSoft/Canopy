#Requires -Version 5.1
[CmdletBinding()]
param([ValidateSet('PASS','BLOCKED','FAIL')][string]$Status='BLOCKED',[string]$Stage='bootstrap',[switch]$SelfTest)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
function Assert-SafeField([string]$Value) { if ($Value -notmatch '^[a-zA-Z0-9_-]{1,48}$') { throw 'Unsafe status field' } }
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
 'PASS: sanitized GitHub status self-test'; exit 0
}
Assert-SafeField $Stage
if (-not (Get-Command gh.exe -ErrorAction SilentlyContinue)) { Write-Warning 'GitHub CLI unavailable; local log retained'; exit 0 }
& gh.exe auth status --hostname github.com 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Warning 'GitHub not authenticated; local log retained'; exit 0 }
$body=New-StatusBody $Status $Stage
& gh.exe issue create --repo 'DevTunaSoft/Canopy' --title ('Canopy checkpoint: '+$Status+' / '+$Stage) --body $body
if ($LASTEXITCODE -ne 0) { throw 'GitHub status publication failed' }
