#Requires -Version 5.1
<#
.SYNOPSIS
Attach an already remastered Canopy Mint ISO to the existing disposable VM.
No disk creation, partitioning, snapshots, or VirtualBox unattended media generation.
#>
[CmdletBinding()]
param(
 [Parameter(Mandatory=$true)][string]$IsoPath,
 [Parameter(Mandatory=$true)][string]$IsoSha256,
 [switch]$Start,
 [switch]$SelfTest
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
function Assert-Input([string]$Path,[string]$Hash) {
 if (-not $Path -or $Hash -notmatch '^[a-fA-F0-9]{64}$') {
   throw 'Prepared ISO and independently verified SHA256 required'
 }
}
function Assert-DedicatedDisk([string]$VmInfo,[string]$ExpectedDisk) {
 $diskRows = @($VmInfo -split "\r?\n" | Where-Object { $_ -match '^"SATA-0-0"=' })
 if ($diskRows.Count -ne 1) { throw 'Missing or ambiguous dedicated disk' }
 $actual = ($diskRows[0] -split '=',2)[1].Trim('"')
 if (-not [string]::Equals([IO.Path]::GetFullPath($actual),[IO.Path]::GetFullPath($ExpectedDisk),[StringComparison]::OrdinalIgnoreCase)) {
  throw 'Unexpected virtual disk path; refusing installer boot'
 }
}
function Test-SameIsoPath([string]$Left,[string]$Right) {
 if (-not $Left -or -not $Right) { return $false }
 return [string]::Equals([IO.Path]::GetFullPath($Left),[IO.Path]::GetFullPath($Right),[StringComparison]::OrdinalIgnoreCase)
}
function Assert-AttachedIso([string]$VmInfo,[string]$ExpectedIso) {
 $rows = @($VmInfo -split "\r?\n" | Where-Object { $_ -match '^"SATA-1-0"=' })
 if ($rows.Count -ne 1) { throw 'DVD attachment readback missing or ambiguous' }
 $actual = ($rows[0] -split '=',2)[1].Trim('"')
 if (-not (Test-SameIsoPath $actual $ExpectedIso)) { throw 'Prepared ISO attachment readback mismatch' }
}
function Assert-ReadyToBoot([string]$VmInfo,[string]$ExpectedDisk,[string]$ExpectedIso) {
 if ($VmInfo -notmatch '(?m)^VMState="poweroff"\s*
 $blocked = $false
 try { Assert-Input '' 'invalid' } catch { $blocked = $true }
 if (-not $blocked) { throw 'Missing hash was accepted' }
 Assert-Input 'C:\\prepared.iso' ('a' * 64)
 Assert-DedicatedDisk '"SATA-0-0"="C:\CanopyTestLab\Canopy-Test-Mint.vdi"' 'C:\CanopyTestLab\Canopy-Test-Mint.vdi'
 $blocked = $false
 try { Assert-DedicatedDisk '"SATA-0-0"="C:\OtherVM\private.vdi"' 'C:\CanopyTestLab\Canopy-Test-Mint.vdi' } catch { $blocked = $true }
 if (-not $blocked) { throw 'Unrelated VM disk accepted' }
 if (-not (Test-SameIsoPath 'C:\\Images\\CANOPY.ISO' 'c:\\images\\canopy.iso')) { throw 'Case-insensitive ISO path comparison regression' }
 if (Test-SameIsoPath 'C:\\Images\\canopy.iso' 'C:\\Other\\canopy.iso') { throw 'Unrelated ISO path accepted' }
 Assert-AttachedIso '"SATA-1-0"="C:\CanopyTestLab\prepared.iso"' 'c:\canopytestlab\PREPARED.iso'
 $blocked = $false
 try { Assert-AttachedIso '"SATA-1-0"="C:\Other\wrong.iso"' 'C:\CanopyTestLab\prepared.iso' } catch { $blocked = $true }
 if (-not $blocked) { throw 'Incorrect DVD readback accepted' }
 $blocked = $false
 try { Assert-AttachedIso '"SATA-1-0"="C:\CanopyTestLab\prepared.iso"`n"SATA-1-0"="C:\CanopyTestLab\prepared.iso"' 'C:\CanopyTestLab\prepared.iso' } catch { $blocked = $true }
 if (-not $blocked) { throw 'Ambiguous DVD readback accepted' }
 Assert-ReadyToBoot ("VMState=`"poweroff`"`nfirmware=`"BIOS`"`n`"SATA-0-0`"=`"C:\CanopyTestLab\Canopy-Test-Mint.vdi`"`n`"SATA-1-0`"=`"C:\CanopyTestLab\prepared.iso`"") 'C:\CanopyTestLab\Canopy-Test-Mint.vdi' 'C:\CanopyTestLab\prepared.iso'
 $blocked = $false
 try { Assert-ReadyToBoot ("VMState=`"running`"`nfirmware=`"BIOS`"`n`"SATA-0-0`"=`"C:\CanopyTestLab\Canopy-Test-Mint.vdi`"`n`"SATA-1-0`"=`"C:\CanopyTestLab\prepared.iso`"") 'C:\CanopyTestLab\Canopy-Test-Mint.vdi' 'C:\CanopyTestLab\prepared.iso' } catch { $blocked = $true }
 if (-not $blocked) { throw 'Running VM accepted during preboot readback' }
 'PASS: prepared ISO attachment and dedicated disk isolation gates'
 exit 0
}
Assert-Input $IsoPath $IsoSha256
$iso = (Resolve-Path -LiteralPath $IsoPath -ErrorAction Stop).ProviderPath
if (-not $iso.EndsWith('.iso',[StringComparison]::OrdinalIgnoreCase)) { throw 'Expected ISO extension' }
if ((Get-FileHash -LiteralPath $iso -Algorithm SHA256).Hash -ne $IsoSha256.ToUpperInvariant()) { throw 'ISO checksum mismatch' }
$vbox = Join-Path $env:ProgramFiles 'Oracle\VirtualBox\VBoxManage.exe'
if (-not (Test-Path -LiteralPath $vbox -PathType Leaf)) { throw 'VirtualBox missing' }
$info = @(& $vbox showvminfo 'Canopy-Test-Mint' '--machinereadable')
if ($LASTEXITCODE -ne 0) { throw 'Dedicated VM not found' }
$raw = $info | Out-String
if ($raw -notmatch '(?m)^VMState="poweroff"\s*$') { throw 'Dedicated VM must be powered off' }
if ($raw -notmatch '(?m)^firmware="BIOS"\s*$') { throw 'Only the verified BIOS test-VM configuration is supported' }
$expectedDisk = Join-Path $env:LOCALAPPDATA 'CanopyTestLab\VirtualMachines\Canopy-Test-Mint.vdi'
Assert-DedicatedDisk $raw $expectedDisk
$dvd = @($info | Where-Object { $_ -match '^"SATA-1-0"=' })
if ($dvd.Count -ne 1) { throw 'Expected one SATA port 1 DVD attachment' }
$previous = ($dvd[0] -split '=',2)[1].Trim('"')
if ($previous -and $previous -ne 'none' -and $previous -ne 'emptydrive' -and -not (Test-Path -LiteralPath $previous -PathType Leaf)) {
 throw 'Existing DVD path cannot be verified; refusing to change it'
}
if (Test-SameIsoPath $previous $iso) { 'Prepared ISO already attached' }
else {
 & $vbox storageattach 'Canopy-Test-Mint' '--storagectl=SATA' '--port=1' '--device=0' '--type=dvddrive' ('--medium=' + $iso)
 if ($LASTEXITCODE -ne 0) { throw 'Failed to attach prepared ISO' }
}
$verifiedInfo = @(& $vbox showvminfo 'Canopy-Test-Mint' '--machinereadable')
if ($LASTEXITCODE -ne 0) { throw 'Cannot verify prepared ISO attachment' }
Assert-ReadyToBoot ($verifiedInfo | Out-String) $expectedDisk $iso
if ($Start) {
 & $vbox modifyvm 'Canopy-Test-Mint' '--boot1=dvd' '--boot2=disk'
 if ($LASTEXITCODE -ne 0) { throw 'Unable to set DVD boot priority' }
 & $vbox startvm 'Canopy-Test-Mint' '--type=gui'
 if ($LASTEXITCODE -ne 0) { throw 'VM start failed' }
 'VM started. Actual guest installation and boot still require verification.'
} else { 'Prepared ISO attached; VM not started.' }
) { throw 'VM state changed before boot; refusing to start' }
 if ($VmInfo -notmatch '(?m)^firmware="BIOS"\s*
 $blocked = $false
 try { Assert-Input '' 'invalid' } catch { $blocked = $true }
 if (-not $blocked) { throw 'Missing hash was accepted' }
 Assert-Input 'C:\\prepared.iso' ('a' * 64)
 Assert-DedicatedDisk '"SATA-0-0"="C:\CanopyTestLab\Canopy-Test-Mint.vdi"' 'C:\CanopyTestLab\Canopy-Test-Mint.vdi'
 $blocked = $false
 try { Assert-DedicatedDisk '"SATA-0-0"="C:\OtherVM\private.vdi"' 'C:\CanopyTestLab\Canopy-Test-Mint.vdi' } catch { $blocked = $true }
 if (-not $blocked) { throw 'Unrelated VM disk accepted' }
 if (-not (Test-SameIsoPath 'C:\\Images\\CANOPY.ISO' 'c:\\images\\canopy.iso')) { throw 'Case-insensitive ISO path comparison regression' }
 if (Test-SameIsoPath 'C:\\Images\\canopy.iso' 'C:\\Other\\canopy.iso') { throw 'Unrelated ISO path accepted' }
 Assert-AttachedIso '"SATA-1-0"="C:\CanopyTestLab\prepared.iso"' 'c:\canopytestlab\PREPARED.iso'
 $blocked = $false
 try { Assert-AttachedIso '"SATA-1-0"="C:\Other\wrong.iso"' 'C:\CanopyTestLab\prepared.iso' } catch { $blocked = $true }
 if (-not $blocked) { throw 'Incorrect DVD readback accepted' }
 $blocked = $false
 try { Assert-AttachedIso '"SATA-1-0"="C:\CanopyTestLab\prepared.iso"`n"SATA-1-0"="C:\CanopyTestLab\prepared.iso"' 'C:\CanopyTestLab\prepared.iso' } catch { $blocked = $true }
 if (-not $blocked) { throw 'Ambiguous DVD readback accepted' }
 'PASS: prepared ISO attachment and dedicated disk isolation gates'
 exit 0
}
Assert-Input $IsoPath $IsoSha256
$iso = (Resolve-Path -LiteralPath $IsoPath -ErrorAction Stop).ProviderPath
if (-not $iso.EndsWith('.iso',[StringComparison]::OrdinalIgnoreCase)) { throw 'Expected ISO extension' }
if ((Get-FileHash -LiteralPath $iso -Algorithm SHA256).Hash -ne $IsoSha256.ToUpperInvariant()) { throw 'ISO checksum mismatch' }
$vbox = Join-Path $env:ProgramFiles 'Oracle\VirtualBox\VBoxManage.exe'
if (-not (Test-Path -LiteralPath $vbox -PathType Leaf)) { throw 'VirtualBox missing' }
$info = @(& $vbox showvminfo 'Canopy-Test-Mint' '--machinereadable')
if ($LASTEXITCODE -ne 0) { throw 'Dedicated VM not found' }
$raw = $info | Out-String
if ($raw -notmatch '(?m)^VMState="poweroff"\s*$') { throw 'Dedicated VM must be powered off' }
if ($raw -notmatch '(?m)^firmware="BIOS"\s*$') { throw 'Only the verified BIOS test-VM configuration is supported' }
$expectedDisk = Join-Path $env:LOCALAPPDATA 'CanopyTestLab\VirtualMachines\Canopy-Test-Mint.vdi'
Assert-DedicatedDisk $raw $expectedDisk
$dvd = @($info | Where-Object { $_ -match '^"SATA-1-0"=' })
if ($dvd.Count -ne 1) { throw 'Expected one SATA port 1 DVD attachment' }
$previous = ($dvd[0] -split '=',2)[1].Trim('"')
if ($previous -and $previous -ne 'none' -and $previous -ne 'emptydrive' -and -not (Test-Path -LiteralPath $previous -PathType Leaf)) {
 throw 'Existing DVD path cannot be verified; refusing to change it'
}
if (Test-SameIsoPath $previous $iso) { 'Prepared ISO already attached' }
else {
 & $vbox storageattach 'Canopy-Test-Mint' '--storagectl=SATA' '--port=1' '--device=0' '--type=dvddrive' ('--medium=' + $iso)
 if ($LASTEXITCODE -ne 0) { throw 'Failed to attach prepared ISO' }
}
$verifiedInfo = @(& $vbox showvminfo 'Canopy-Test-Mint' '--machinereadable')
if ($LASTEXITCODE -ne 0) { throw 'Cannot verify prepared ISO attachment' }
Assert-AttachedIso ($verifiedInfo | Out-String) $iso
if ($Start) {
 & $vbox modifyvm 'Canopy-Test-Mint' '--boot1=dvd' '--boot2=disk'
 if ($LASTEXITCODE -ne 0) { throw 'Unable to set DVD boot priority' }
 & $vbox startvm 'Canopy-Test-Mint' '--type=gui'
 if ($LASTEXITCODE -ne 0) { throw 'VM start failed' }
 'VM started. Actual guest installation and boot still require verification.'
} else { 'Prepared ISO attached; VM not started.' }
) { throw 'VM firmware changed before boot' }
 Assert-DedicatedDisk $VmInfo $ExpectedDisk
 Assert-AttachedIso $VmInfo $ExpectedIso
}
if ($SelfTest) {
 $blocked = $false
 try { Assert-Input '' 'invalid' } catch { $blocked = $true }
 if (-not $blocked) { throw 'Missing hash was accepted' }
 Assert-Input 'C:\\prepared.iso' ('a' * 64)
 Assert-DedicatedDisk '"SATA-0-0"="C:\CanopyTestLab\Canopy-Test-Mint.vdi"' 'C:\CanopyTestLab\Canopy-Test-Mint.vdi'
 $blocked = $false
 try { Assert-DedicatedDisk '"SATA-0-0"="C:\OtherVM\private.vdi"' 'C:\CanopyTestLab\Canopy-Test-Mint.vdi' } catch { $blocked = $true }
 if (-not $blocked) { throw 'Unrelated VM disk accepted' }
 if (-not (Test-SameIsoPath 'C:\\Images\\CANOPY.ISO' 'c:\\images\\canopy.iso')) { throw 'Case-insensitive ISO path comparison regression' }
 if (Test-SameIsoPath 'C:\\Images\\canopy.iso' 'C:\\Other\\canopy.iso') { throw 'Unrelated ISO path accepted' }
 Assert-AttachedIso '"SATA-1-0"="C:\CanopyTestLab\prepared.iso"' 'c:\canopytestlab\PREPARED.iso'
 $blocked = $false
 try { Assert-AttachedIso '"SATA-1-0"="C:\Other\wrong.iso"' 'C:\CanopyTestLab\prepared.iso' } catch { $blocked = $true }
 if (-not $blocked) { throw 'Incorrect DVD readback accepted' }
 $blocked = $false
 try { Assert-AttachedIso '"SATA-1-0"="C:\CanopyTestLab\prepared.iso"`n"SATA-1-0"="C:\CanopyTestLab\prepared.iso"' 'C:\CanopyTestLab\prepared.iso' } catch { $blocked = $true }
 if (-not $blocked) { throw 'Ambiguous DVD readback accepted' }
 'PASS: prepared ISO attachment and dedicated disk isolation gates'
 exit 0
}
Assert-Input $IsoPath $IsoSha256
$iso = (Resolve-Path -LiteralPath $IsoPath -ErrorAction Stop).ProviderPath
if (-not $iso.EndsWith('.iso',[StringComparison]::OrdinalIgnoreCase)) { throw 'Expected ISO extension' }
if ((Get-FileHash -LiteralPath $iso -Algorithm SHA256).Hash -ne $IsoSha256.ToUpperInvariant()) { throw 'ISO checksum mismatch' }
$vbox = Join-Path $env:ProgramFiles 'Oracle\VirtualBox\VBoxManage.exe'
if (-not (Test-Path -LiteralPath $vbox -PathType Leaf)) { throw 'VirtualBox missing' }
$info = @(& $vbox showvminfo 'Canopy-Test-Mint' '--machinereadable')
if ($LASTEXITCODE -ne 0) { throw 'Dedicated VM not found' }
$raw = $info | Out-String
if ($raw -notmatch '(?m)^VMState="poweroff"\s*$') { throw 'Dedicated VM must be powered off' }
if ($raw -notmatch '(?m)^firmware="BIOS"\s*$') { throw 'Only the verified BIOS test-VM configuration is supported' }
$expectedDisk = Join-Path $env:LOCALAPPDATA 'CanopyTestLab\VirtualMachines\Canopy-Test-Mint.vdi'
Assert-DedicatedDisk $raw $expectedDisk
$dvd = @($info | Where-Object { $_ -match '^"SATA-1-0"=' })
if ($dvd.Count -ne 1) { throw 'Expected one SATA port 1 DVD attachment' }
$previous = ($dvd[0] -split '=',2)[1].Trim('"')
if ($previous -and $previous -ne 'none' -and $previous -ne 'emptydrive' -and -not (Test-Path -LiteralPath $previous -PathType Leaf)) {
 throw 'Existing DVD path cannot be verified; refusing to change it'
}
if (Test-SameIsoPath $previous $iso) { 'Prepared ISO already attached' }
else {
 & $vbox storageattach 'Canopy-Test-Mint' '--storagectl=SATA' '--port=1' '--device=0' '--type=dvddrive' ('--medium=' + $iso)
 if ($LASTEXITCODE -ne 0) { throw 'Failed to attach prepared ISO' }
}
$verifiedInfo = @(& $vbox showvminfo 'Canopy-Test-Mint' '--machinereadable')
if ($LASTEXITCODE -ne 0) { throw 'Cannot verify prepared ISO attachment' }
Assert-AttachedIso ($verifiedInfo | Out-String) $iso
if ($Start) {
 & $vbox modifyvm 'Canopy-Test-Mint' '--boot1=dvd' '--boot2=disk'
 if ($LASTEXITCODE -ne 0) { throw 'Unable to set DVD boot priority' }
 & $vbox startvm 'Canopy-Test-Mint' '--type=gui'
 if ($LASTEXITCODE -ne 0) { throw 'VM start failed' }
 'VM started. Actual guest installation and boot still require verification.'
} else { 'Prepared ISO attached; VM not started.' }
