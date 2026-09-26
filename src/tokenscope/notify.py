"""Desktop notifications (Windows only; a silent no-op elsewhere).

Text travels through environment variables and the script through
`-EncodedCommand`, so there is no shell quoting anywhere: Chinese titles and
project names survive, and nothing a repo is called can break out of the
script. Windows PowerShell 5.1 is required for the WinRT toast API; if that
fails we fall back to a tray balloon, and if that fails we return False.
"""
from __future__ import annotations

import base64
import os
import subprocess
import sys

_TOAST_PS = r"""
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$t = $xml.GetElementsByTagName('text')
$t.Item(0).AppendChild($xml.CreateTextNode($env:TS_TOAST_TITLE)) | Out-Null
$t.Item(1).AppendChild($xml.CreateTextNode($env:TS_TOAST_BODY)) | Out-Null
if ($env:TS_TOAST_URL) {
  $xml.DocumentElement.SetAttribute('activationType', 'protocol')
  $xml.DocumentElement.SetAttribute('launch', $env:TS_TOAST_URL)
}
$appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)
"""

_BALLOON_PS = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$n = New-Object System.Windows.Forms.NotifyIcon
$n.Icon = [System.Drawing.SystemIcons]::Information
$n.Visible = $true
$n.ShowBalloonTip(8000, $env:TS_TOAST_TITLE, $env:TS_TOAST_BODY, [System.Windows.Forms.ToolTipIcon]::Info)
Start-Sleep -Seconds 9
$n.Dispose()
"""


def _encode(script: str) -> str:
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


def _run_ps(script: str, env: dict, timeout: float) -> bool:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    r = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-EncodedCommand", _encode(script)],
        capture_output=True, timeout=timeout, creationflags=flags, env=env,
    )
    return r.returncode == 0


def toast(title: str, body: str, launch_url: str | None = None, timeout: float = 10.0) -> bool:
    """Show a Windows toast. Returns True when a notification was displayed."""
    if sys.platform != "win32":
        return False
    env = {**os.environ, "TS_TOAST_TITLE": title or "TokenScope", "TS_TOAST_BODY": body or "",
           "TS_TOAST_URL": launch_url or ""}
    try:
        if _run_ps(_TOAST_PS, env, timeout):
            return True
        return _run_ps(_BALLOON_PS, env, timeout + 10)
    except Exception:  # noqa: BLE001 — notifications are best-effort
        return False
