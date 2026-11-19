#Requires -Version 5.1
[CmdletBinding()]
param([ValidateSet('PASS','BLOCKED','FAIL')][string]$Status,[ValidateSet('launcher','wsl','iso','vm','desktop')][string]$Stage='launcher',[switch]$SelfTest)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
function New-Checkpoint([string]$State,[string]$Step) {
 return [ordered]@{schema_version=1;status=$State;stage=$Step;timestamp_utc=[DateTime]::UtcNow.ToString('o');vm='Canopy-Test-Mint';desktop_boot_verified=$false}
}
if ($SelfTest) {
 $result=New-Checkpoint 'PASS' 'launcher'
 if ($result.desktop_boot_verified -ne $false -or $result.status -ne 'PASS') { throw 'Checkpoint contract failed' }
 'PASS: local checkpoint contract'; exit 0
}
$dir=Join-Path $env:LOCALAPPDATA 'CanopyTestLab\diagnostics'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$target=Join-Path $dir 'last-checkpoint.json'
$temporary=Join-Path $dir ('checkpoint-'+[guid]::NewGuid().ToString('N')+'.tmp')
try {
 New-Checkpoint $Status $Stage | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $temporary -Encoding UTF8
 Move-Item -LiteralPath $temporary -Destination $target -Force
} finally { Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue }
Write-Host ('Canopy checkpoint saved: '+$target)
