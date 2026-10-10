"""Small system adapters: clock, desktop notifications (macOS / Windows / Linux), .env loading."""

import base64
import json
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path


class SystemClock:
    def today(self) -> date:
        return date.today()


class MacNotifier:
    def notify(self, title: str, body: str) -> None:
        script = f"display notification {json.dumps(body)} with title {json.dumps(title)}"
        subprocess.run(["osascript", "-e", script], check=False, capture_output=True)


class WindowsNotifier:
    """Toast notification through Windows PowerShell (built into Windows 10/11).

    Title and body travel in environment variables and are XML-escaped inside the
    script, so task text can never be run as PowerShell."""

    # Passed as -EncodedCommand (base64 UTF-16LE), so no shell quoting is involved.
    _SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[void][Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
[void][Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime]
$t = [Security.SecurityElement]::Escape($env:SEASON_TOAST_TITLE)
$b = [Security.SecurityElement]::Escape($env:SEASON_TOAST_BODY)
$x = New-Object Windows.Data.Xml.Dom.XmlDocument
$x.LoadXml("<toast><visual><binding template='ToastGeneric'><text>$t</text><text>$b</text></binding></visual></toast>")
$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show(
    [Windows.UI.Notifications.ToastNotification]::new($x))
"""

    @classmethod
    def command(cls) -> list[str]:
        encoded = base64.b64encode(cls._SCRIPT.encode("utf-16-le")).decode("ascii")
        return ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded]

    def notify(self, title: str, body: str) -> None:
        env = {**os.environ, "SEASON_TOAST_TITLE": title, "SEASON_TOAST_BODY": body}
        try:
            subprocess.run(self.command(), env=env, check=False, capture_output=True, timeout=20,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.TimeoutExpired):
            pass  # a missed reminder is not worth crashing over


class LinuxNotifier:
    def notify(self, title: str, body: str) -> None:
        if shutil.which("notify-send"):
            subprocess.run(["notify-send", title, body], check=False, capture_output=True)


class SilentNotifier:
    def notify(self, title: str, body: str) -> None:
        return None


def default_notifier():
    """The desktop notifier for this OS."""
    if sys.platform == "darwin":
        return MacNotifier()
    if sys.platform == "win32":
        return WindowsNotifier()
    return LinuxNotifier()


def load_dotenv(path: Path) -> None:
    """KEY=VALUE lines into os.environ. Existing variables win. Values never logged."""
    if not path.is_file():
        return
    # utf-8-sig: Windows Notepad saves .env with a byte-order mark
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        os.environ.setdefault(key, value)
