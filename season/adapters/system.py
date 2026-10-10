"""Small system adapters: clock, macOS notifications, .env loading."""

import json
import os
import subprocess
from datetime import date
from pathlib import Path


class SystemClock:
    def today(self) -> date:
        return date.today()


class MacNotifier:
    def notify(self, title: str, body: str) -> None:
        script = f"display notification {json.dumps(body)} with title {json.dumps(title)}"
        subprocess.run(["osascript", "-e", script], check=False, capture_output=True)


class SilentNotifier:
    def notify(self, title: str, body: str) -> None:
        return None


def load_dotenv(path: Path) -> None:
    """KEY=VALUE lines into os.environ. Existing variables win. Values never logged."""
    if not path.is_file():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        os.environ.setdefault(key, value)
