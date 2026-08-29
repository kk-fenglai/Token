#!/bin/bash
# TokenScope 一键启动(macOS):双击本文件即可。
# 首次使用请先在终端执行:chmod +x scripts/start.command
# 已在运行时不重复启动,只打开浏览器。
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if lsof -iTCP:8787 -sTCP:LISTEN >/dev/null 2>&1; then
  open "http://localhost:8787"
  exit 0
fi

if [ ! -x "$ROOT/.venv/bin/python" ]; then
  echo ".venv 不存在,先创建虚拟环境…"
  cd "$ROOT"
  python3 -m venv .venv
  ./.venv/bin/python -m pip install -e ".[dev]"
fi

# 稍等服务起来再开浏览器
( sleep 2; open "http://localhost:8787" ) &
exec "$ROOT/.venv/bin/tokenscope-web" --port 8787
