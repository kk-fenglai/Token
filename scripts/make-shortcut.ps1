# Rebuild the TokenScope desktop shortcut.
# All paths derive from $PSScriptRoot, so nothing depends on console encoding.
$ErrorActionPreference = "Stop"
$scripts = $PSScriptRoot

# Keep the icon at an ASCII-only, non-synced path: %LOCALAPPDATA%\TokenScope
$iconDir = Join-Path $env:LOCALAPPDATA "TokenScope"
New-Item -ItemType Directory -Force -Path $iconDir | Out-Null
$icon = Join-Path $iconDir "tokenscope.ico"
Copy-Item (Join-Path $scripts "tokenscope-v2.ico") $icon -Force

$desktop = [Environment]::GetFolderPath("Desktop")
$lnkPath = Join-Path $desktop "TokenScope.lnk"
if (Test-Path $lnkPath) { Remove-Item $lnkPath -Force }

# WScript.Shell stores shortcut strings via the ANSI codepage, so any
# character outside it (like the Chinese folder name) becomes a literal '?'
# and the shortcut silently fails. Fix: junction an ASCII-only path to the
# project and reference everything through it.
$junction = Join-Path $iconDir "app"
$projRoot = Split-Path $scripts -Parent
if (-not (Test-Path $junction)) {
  New-Item -ItemType Junction -Path $junction -Target $projRoot | Out-Null
}

$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut($lnkPath)
$lnk.TargetPath = Join-Path $junction "scripts\start.cmd"
$lnk.WorkingDirectory = Join-Path $junction "scripts"
$lnk.IconLocation = "$icon,0"
$lnk.Description = "TokenScope dashboard"
$lnk.WindowStyle = 7
$lnk.Save()

# Verify what actually got stored
$check = $ws.CreateShortcut($lnkPath)
Write-Host "lnk       : $lnkPath"
Write-Host "target    : $($check.TargetPath)"
Write-Host "ascii ok  : $(-not ([int[]][char[]]$check.TargetPath -gt 127).Count)"
Write-Host "script ok : $(Test-Path -LiteralPath $check.TargetPath)"
Write-Host "icon ok   : $(Test-Path ($check.IconLocation -replace ',\d+$'))"
