@echo off
rem TokenScope launcher - plain cmd, no PowerShell (AV-friendly).
rem Logs to %LOCALAPPDATA%\TokenScope\launch.log
set "ROOT=%~dp0.."
set "LOGDIR=%LOCALAPPDATA%\TokenScope"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
set "LOG=%LOGDIR%\launch.log"
echo [%date% %time%] start.cmd launched>>"%LOG%"

netstat -ano | findstr /r /c:":8787 .*LISTENING" >nul 2>&1
if %errorlevel%==0 (
  echo [%date% %time%] already running, opening browser>>"%LOG%"
  start "" http://localhost:8787
  exit /b 0
)

if not exist "%ROOT%\.venv\Scripts\tokenscope-web.exe" (
  echo [%date% %time%] venv missing>>"%LOG%"
  echo .venv not found. Run scripts\start.ps1 once to set it up.
  pause
  exit /b 1
)

echo [%date% %time%] starting server>>"%LOG%"
start "TokenScope" /min "%ROOT%\.venv\Scripts\tokenscope-web.exe" --port 8787
rem Give the server a moment before opening the browser
timeout /t 2 /nobreak >nul
start "" http://localhost:8787
exit /b 0
