"""Start the board server.  Usage: uv run serve.py  (launchd runs .venv/bin/python serve.py)"""

from season.config import load_settings
from season.container import build_app
from season.interfaces.http.server import serve

if __name__ == "__main__":
    serve(build_app(load_settings()))
