#!/usr/bin/env sh
# Register a daily cron entry that runs `tokenscope-sync`, so transcripts are
# captured into the TokenScope database even when the dashboard is never
# opened (Claude Code prunes transcripts after ~30 days).
#
# Usage:  sh scripts/install-autosync.sh          # install (09:00 daily)
#         sh scripts/install-autosync.sh --remove
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EXE="$ROOT/.venv/bin/tokenscope-sync"
TAG="# tokenscope-autosync"

if [ "$1" = "--remove" ]; then
  crontab -l 2>/dev/null | grep -v "$TAG" | crontab -
  echo "removed cron entry"
  exit 0
fi

if [ ! -x "$EXE" ]; then
  echo "tokenscope-sync not found at $EXE — run scripts/start.command once first" >&2
  exit 1
fi

( crontab -l 2>/dev/null | grep -v "$TAG"; echo "0 9 * * * \"$EXE\" --quiet $TAG" ) | crontab -
echo "installed: 0 9 * * * $EXE --quiet"
echo "Tip: raise Claude Code's transcript retention in ~/.claude/settings.json: { \"cleanupPeriodDays\": 365 }"
