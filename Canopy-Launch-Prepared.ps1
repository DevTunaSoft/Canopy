#Requires -Version 5.1
<#
.SYNOPSIS
Interactive one-click handoff for a previously remastered, disposable-VM-only ISO.
Requires an explicit confirmation because the ISO contains automatic disk partitioning.
#>
[CmdletBinding()]
param([switch]$SelfTest)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
function Assert-PreparedImage([string]$Path) {
 if (-not $Path -or -not $Path.EndsWith('.iso',[StringComparison]::OrdinalIgnoreCase)) {
  throw 'Select a prepared Canopy .iso file'
 }
 if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw 'Prepared ISO not found' }
 $name = [IO.Path]::GetFileName($Path)
 if ($name -notmatch '^canopy-.*\.iso$') { throw 'Prepared ISO filename must begin canopy-; original Mint ISO is not supported' }
}
if ($SelfTest) {
 $blocked = $false
 try { Assert-PreparedImage 'C:\\linuxmint-original.iso' } catch { $blocked = $true }
 if (-not $blocked) { throw 'Original Mint ISO was accepted' }
 'PASS: prepared image selection safety'
 exit 0
}
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.Title = 'Choose prepared Canopy disposable-VM installer ISO'
$dialog.Filter = 'Canopy installer ISO (canopy-*.iso)|canopy-*.iso'
$dialog.CheckFileExists = $true
if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
 'No changes made; file selection canceled.'
 exit 0
}
$iso = $dialog.FileName
Assert-PreparedImage $iso
$hash = (Get-FileHash -LiteralPath $iso -Algorithm SHA256).Hash
$question = "This installer is configured for automatic partitioning of the dedicated Canopy-Test-Mint virtual disk. Do not use it on a physical computer. Continue attaching and starting the VM?"
$answer = [System.Windows.Forms.MessageBox]::Show($question,'Canopy disposable VM installation',[System.Windows.Forms.MessageBoxButtons]::YesNo,[System.Windows.Forms.MessageBoxIcon]::Warning)
if ($answer -ne [System.Windows.Forms.DialogResult]::Yes) { 'Canceled; no changes made.'; exit 0 }
$attach = Join-Path $PSScriptRoot 'scripts\Attach-CanopyPreparedISO.ps1'
& $attach -IsoPath $iso -IsoSha256 $hash -Start
if ($LASTEXITCODE -ne 0) { throw 'Prepared ISO VM launch failed' }
