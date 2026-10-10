"""Start the board server.  Usage: uv run serve.py

Background launchers run it without a console (launchd on macOS, pythonw.exe on
Windows). pythonw has no stdout/stderr at all, so errors then go to server.log.
"""

import sys
from pathlib import Path

if sys.stderr is None or sys.stdout is None:
    log = open(Path(__file__).resolve().parent / "server.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115
    sys.stdout = sys.stdout or log
    sys.stderr = sys.stderr or log

from season.config import load_settings  # noqa: E402
from season.container import build_app  # noqa: E402
from season.interfaces.http.server import serve  # noqa: E402

if __name__ == "__main__":
    serve(build_app(load_settings()))
