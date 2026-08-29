# TokenScope 生产模式:单进程 localhost:8787,自动打开浏览器
# 已在运行时不重复启动,只打开浏览器。
# 每次启动写日志到 %LOCALAPPDATA%\TokenScope\launch.log,便于排查双击无反应的问题。
$root = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $env:LOCALAPPDATA "TokenScope"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir "launch.log"
function Log($msg) { Add-Content -Path $log -Value ("[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg) }

Log "--- launched (pid=$PID) ---"
try {
  $listening = Get-NetTCPConnection -LocalPort 8787 -State Listen -ErrorAction SilentlyContinue
  if ($listening) {
    Log "port 8787 already listening -> open browser only"
    Start-Process "http://localhost:8787"
    Log "browser opened, exiting"
    exit 0
  }

  if (-not (Test-Path "$root\.venv\Scripts\python.exe")) {
    Log "no .venv, creating"
    Write-Host ".venv 不存在,先创建虚拟环境…" -ForegroundColor Yellow
    Push-Location $root
    python -m venv .venv
    .\.venv\Scripts\python -m pip install -e ".[dev]"
    Pop-Location
  }

  Log "starting server"
  Start-Process "http://localhost:8787"
  & "$root\.venv\Scripts\tokenscope-web.exe" --port 8787
  Log "server exited"
} catch {
  Log "ERROR: $($_.Exception.Message)"
  throw
}
