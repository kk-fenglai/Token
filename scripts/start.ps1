# TokenScope 生产模式:单进程 localhost:8787,自动打开浏览器
$root = Split-Path -Parent $PSScriptRoot

if (-not (Test-Path "$root\.venv\Scripts\python.exe")) {
  Write-Host ".venv 不存在,先创建虚拟环境…" -ForegroundColor Yellow
  Push-Location $root
  python -m venv .venv
  .\.venv\Scripts\python -m pip install -e ".[dev]"
  Pop-Location
}

Start-Process "http://localhost:8787"
& "$root\.venv\Scripts\tokenscope-web.exe" --port 8787
