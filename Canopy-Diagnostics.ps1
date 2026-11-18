#Requires -Version 5.1
# Double-clickable, read-only diagnostic collector for the dedicated Canopy test VM.
$ErrorActionPreference = 'Stop'
$base = Join-Path $env:LOCALAPPDATA 'CanopyTestLab'
$out = Join-Path $env:USERPROFILE ('Desktop\Canopy-Diagnostics-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.zip')
$tmp = Join-Path ([IO.Path]::GetTempPath()) ('CanopyDiag-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tmp -Force | Out-Null
function Save-Result([string]$Name, [scriptblock]$Action) {
  try {
    $result = & $Action 2>&1 | Out-String
    $result = $result -replace [regex]::Escape($env:USERPROFILE), '%USERPROFILE%'
    [IO.File]::WriteAllText((Join-Path $tmp $Name), $result)
  } catch {
    [IO.File]::WriteAllText((Join-Path $tmp $Name), ('ERROR: ' + $_.Exception.GetType().Name))
  }
}
try {
  Save-Result 'host.txt' {
    'Canopy diagnostic version: 1'
    'OS: ' + [Environment]::OSVersion.VersionString
    'PowerShell: ' + $PSVersionTable.PSVersion.ToString()
    'UTC: ' + [DateTime]::UtcNow.ToString('o')
  }
  $vbox = Join-Path $env:ProgramFiles 'Oracle\VirtualBox\VBoxManage.exe'
  Save-Result 'virtualbox.txt' {
    if (-not (Test-Path -LiteralPath $vbox)) { 'VirtualBox not found' }
    else {
      & $vbox --version
      $lines = & $vbox showvminfo 'Canopy-Test-Mint' --machinereadable
      if ($LASTEXITCODE -ne 0) { 'Canopy VM not found' }
      else {
        $lines | Where-Object { $_ -match '^(VMState|firmware|memory|cpus|SATA-|storagecontroller|boot[1-4]|ostype)=' } |
          ForEach-Object { $_ -replace [regex]::Escape($env:USERPROFILE), '%USERPROFILE%' }
      }
    }
  }
  Save-Result 'repository.txt' {
    $repo = Join-Path $base 'source'
    if (-not (Test-Path (Join-Path $repo '.git'))) { 'Canopy repository not found' }
    else {
      & git -C $repo rev-parse --short HEAD
      & git -C $repo branch --show-current
      & git -C $repo status --short
    }
  }
  Save-Result 'iso.txt' {
    $iso = Join-Path $env:USERPROFILE 'Downloads\linuxmint-22.3-cinnamon-64bit (1).iso'
    if (Test-Path -LiteralPath $iso -PathType Leaf) {
      'ISO present'
      'SHA256: ' + (Get-FileHash -LiteralPath $iso -Algorithm SHA256).Hash
      'Bytes: ' + (Get-Item -LiteralPath $iso).Length
    } else { 'Expected ISO not found' }
  }
  [IO.File]::WriteAllText((Join-Path $tmp 'README.txt'), 'Read-only diagnostics. No passwords, environment dumps, guest logs, or VM disk contents collected. Review ZIP before sharing.')
  if (Test-Path -LiteralPath $out) { throw 'Diagnostic destination already exists' }
  Compress-Archive -Path (Join-Path $tmp '*') -DestinationPath $out -CompressionLevel Optimal
  Write-Host ('Diagnostic ZIP created: ' + $out)
} finally {
  Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
