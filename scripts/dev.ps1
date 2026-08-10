# TokenScope 开发模式:后端 :8787 + Vite :5173(/api 代理到后端)
$root = Split-Path -Parent $PSScriptRoot

Start-Process powershell -ArgumentList "-NoExit", "-Command",
  "cd '$root'; .\.venv\Scripts\python -m uvicorn tokenscope.web:app --reload --port 8787"

Start-Process powershell -ArgumentList "-NoExit", "-Command",
  "cd '$root\frontend'; npm run dev"

Write-Host "backend  -> http://localhost:8787"
Write-Host "frontend -> http://localhost:5173"
