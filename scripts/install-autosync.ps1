# Register a Windows scheduled task that runs `tokenscope-sync` daily (and at
# logon), so transcripts are captured into the TokenScope database even when
# the dashboard is never opened. Claude Code prunes transcripts after
# ~cleanupPeriodDays (30 by default); once a month is pruned it is gone for
# good, which shows up as "logs missing" months on the Monthly Bills page.
#
# Usage:  powershell -ExecutionPolicy Bypass -File scripts\install-autosync.ps1
#         powershell -ExecutionPolicy Bypass -File scripts\install-autosync.ps1 -Remove
param([switch]$Remove)

$ErrorActionPreference = "Stop"
$taskName = "TokenScope Sync"
$root = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $root ".venv\Scripts\tokenscope-sync.exe"

if ($Remove) {
  Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
  Write-Host "removed scheduled task '$taskName'"
  exit 0
}

if (-not (Test-Path $exe)) {
  Write-Host "tokenscope-sync.exe not found at $exe" -ForegroundColor Yellow
  Write-Host "Run scripts\start.ps1 once (it creates .venv and installs the package), then retry."
  exit 1
}

$action = New-ScheduledTaskAction -Execute $exe -Argument "--quiet"
$triggers = @(
  (New-ScheduledTaskTrigger -Daily -At 09:00),
  (New-ScheduledTaskTrigger -AtLogOn)
)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
  -MultipleInstances IgnoreNew -RunOnlyIfNetworkAvailable:$false
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $triggers -Settings $settings `
  -Description "Parse new Claude Code transcripts into TokenScope (daily + at logon)" -Force | Out-Null

Write-Host "registered scheduled task '$taskName' -> $exe --quiet (daily 09:00 + at logon)"
Write-Host "Tip: also raise Claude Code's transcript retention in ~/.claude/settings.json:"
Write-Host '     { "cleanupPeriodDays": 365 }'
