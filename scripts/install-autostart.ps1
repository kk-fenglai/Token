# Start TokenScope automatically at logon (current user, no admin needed).
#   powershell -ExecutionPolicy Bypass -File scripts\install-autostart.ps1            # install + start now
#   powershell -ExecutionPolicy Bypass -File scripts\install-autostart.ps1 -Uninstall # remove
# Writes HKCU\...\Run\TokenScope -> pythonw.exe scripts\autostart.pyw (hidden supervisor
# that runs the dashboard on its port and restarts it if it exits).
param([switch]$Uninstall)
$ErrorActionPreference = "Stop"
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$name = "TokenScope"

if ($Uninstall) {
  Remove-ItemProperty -Path $runKey -Name $name -ErrorAction SilentlyContinue
  Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" |
    Where-Object { $_.CommandLine -like "*autostart.pyw*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
  Write-Host "autostart removed (the running dashboard, if any, keeps running)"
  exit 0
}

# Same ASCII-only junction as make-shortcut.ps1, so the command line never
# depends on the Chinese folder name or the console codepage.
$dataDir = Join-Path $env:LOCALAPPDATA "TokenScope"
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
$junction = Join-Path $dataDir "app"
$projRoot = Split-Path $PSScriptRoot -Parent
if (-not (Test-Path $junction)) {
  New-Item -ItemType Junction -Path $junction -Target $projRoot | Out-Null
}

$pythonw = Join-Path $junction ".venv\Scripts\pythonw.exe"
$script = Join-Path $junction "scripts\autostart.pyw"
if (-not (Test-Path $pythonw)) { throw "missing $pythonw - run scripts\start.ps1 once to create the venv" }

$cmd = "`"$pythonw`" `"$script`""
Set-ItemProperty -Path $runKey -Name $name -Value $cmd
Write-Host "Run entry: $cmd"

# Start it now as well; a second copy exits immediately thanks to the lock.
Start-Process -FilePath $pythonw -ArgumentList "`"$script`"" -WorkingDirectory $junction
Write-Host "supervisor started; logs in $dataDir\launch.log and server.log"
