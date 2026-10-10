"""HTTP interface: routes requests to use cases, nothing else.

    GET    /                                   the board UI
    GET    /api/board                          everything the UI needs
    POST   /api/tasks/{id}/slots/{slot}        check a box (today)
    DELETE /api/tasks/{id}/slots/{slot}        uncheck it; the reply carries `undo`
    POST   /api/tasks/{id}/slots/{slot}/restore {d, problem, note}  undo an uncheck
    PUT    /api/tasks/{id}/slots/{slot}/note   {note}        add/change/clear (null or "") the note
    POST   /api/tasks                          {week, text, sessions?, hours?}  add; Jev picks the type
                                               ("Read papers 3x2h" in text also sets the size)
    PUT    /api/tasks/{id}/size                {sessions, hours}  boxes and hours per box
    DELETE /api/tasks/{id}                     remove a task you added
    PUT    /api/tasks/{id}/category            {category}    pick the type by hand
    POST   /api/categories                     {label, description, task_id?}
    PUT    /api/pages                          {pages}
    POST   /api/problems/skip

Writes need the header `X-Requested-With: season` and, when the browser
sends one, an Origin of this server. Other websites can't forge either.
Every write answers with the new board.
"""

import json
import re
from collections.abc import Callable
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from season.container import App
from season.domain.errors import InvalidInput, NotFound
from season.domain.model import SessionMark

from .presenter import Reply, Undo, board_json

WEB = Path(__file__).resolve().parent / "web"
# Files the board page needs besides itself (Home Screen icon, app manifest). Fixed list, no path lookups.
STATIC = {
    "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json"),
    "/apple-touch-icon.png": ("icon-180.png", "image/png"),
    "/icon-192.png": ("icon-192.png", "image/png"),
    "/icon-512.png": ("icon-512.png", "image/png"),
}
MAX_BODY = 16 * 1024

Handler = Callable[[App, re.Match, dict], Reply | None]


def _int(body: dict, key: str) -> int:
    v = body.get(key)
    if isinstance(v, bool) or not isinstance(v, int):
        raise InvalidInput(f"{key} must be a whole number")
    return v


def _str(body: dict, key: str) -> str:
    v = body.get(key)
    if not isinstance(v, str):
        raise InvalidInput(f"{key} must be text")
    return v


def _date(body: dict, key: str) -> date:
    try:
        return date.fromisoformat(_str(body, key))
    except ValueError as exc:
        raise InvalidInput(f"{key} must be a date like 2026-10-12") from exc


def _optional_str(body: dict, key: str) -> str | None:
    v = body.get(key)
    if v is not None and not isinstance(v, str):
        raise InvalidInput(f"{key} must be text")
    return v


def _optional_int(body: dict, key: str) -> int | None:
    return None if body.get(key) is None else _int(body, key)


def _hours(body: dict, key: str) -> float | None:
    v = body.get(key)
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise InvalidInput(f"{key} must be a number")
    return float(v)


def _required_hours(body: dict) -> float:
    hours = _hours(body, "hours")
    if hours is None:
        raise InvalidInput("hours must be a number")
    return hours


def _add_task(app: App, m: re.Match, b: dict) -> Reply | None:
    task = app.add_task(_date(b, "week"), _str(b, "text"), _optional_int(b, "sessions"), _hours(b, "hours"))
    if task.assigned_by == "fallback":
        return Reply("Couldn't tell the type, so it's under other. Click the type to change it.")
    return None


def _unmark(app: App, m: re.Match, b: dict) -> Reply | None:
    task_id, slot = int(m[1]), int(m[2])
    removed = app.unmark_session(task_id, slot)
    return Reply(undo=Undo(task_id, slot, removed)) if removed else None


def _restore(app: App, m: re.Match, b: dict) -> None:
    mark = SessionMark(_date(b, "d"), _optional_int(b, "problem"), _optional_str(b, "note"))
    app.restore_session(int(m[1]), int(m[2]), mark)


def _note(app: App, m: re.Match, b: dict) -> None:
    app.set_session_note(int(m[1]), int(m[2]), _optional_str(b, "note"))


def _create_category(app: App, m: re.Match, b: dict) -> Reply | None:
    task_id = b.get("task_id")
    if task_id is not None and (isinstance(task_id, bool) or not isinstance(task_id, int)):
        raise InvalidInput("task_id must be a whole number")
    result = app.create_category(_str(b, "label"), _str(b, "description"), task_id)
    if result.moved:
        return Reply(f"Moved {result.moved} task{'s' if result.moved != 1 else ''} from other into "
                     f"{result.category.label}.")
    return None


ROUTES: list[tuple[str, re.Pattern, Handler]] = [
    ("POST", re.compile(r"/api/tasks/(\d+)/slots/(\d+)"),
     lambda app, m, b: app.mark_session(int(m[1]), int(m[2]))),
    ("DELETE", re.compile(r"/api/tasks/(\d+)/slots/(\d+)"), _unmark),
    ("POST", re.compile(r"/api/tasks/(\d+)/slots/(\d+)/restore"), _restore),
    ("PUT", re.compile(r"/api/tasks/(\d+)/slots/(\d+)/note"), _note),
    ("POST", re.compile(r"/api/tasks"), _add_task),
    ("DELETE", re.compile(r"/api/tasks/(\d+)"),
     lambda app, m, b: app.remove_task(int(m[1]))),
    ("PUT", re.compile(r"/api/tasks/(\d+)/size"),
     lambda app, m, b: app.resize_task(int(m[1]), _int(b, "sessions"), _required_hours(b))),
    ("PUT", re.compile(r"/api/tasks/(\d+)/category"),
     lambda app, m, b: app.assign_category(int(m[1]), _str(b, "category"))),
    ("POST", re.compile(r"/api/categories"), _create_category),
    ("PUT", re.compile(r"/api/pages"),
     lambda app, m, b: app.set_pages(b.get("pages"))),
    ("POST", re.compile(r"/api/problems/skip"),
     lambda app, m, b: app.skip_problem()),
]


def _route(method: str, path: str) -> tuple[Handler, re.Match] | None:
    for route_method, pattern, handler in ROUTES:
        m = pattern.fullmatch(path)
        if m and route_method == method:
            return handler, m
    return None


def make_handler(app: App) -> type[BaseHTTPRequestHandler]:
    allowed_origins = app.settings.allowed_origins

    class RequestHandler(BaseHTTPRequestHandler):
        server_version = "season"

        def log_message(self, fmt: str, *args) -> None:
            return

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            try:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass  # the page went away mid-response (reload, window closed)

        def _json(self, status: int, payload: dict) -> None:
            self._send(status, json.dumps(payload, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path in ("/", "/board.html"):
                self._send(200, (WEB / "board.html").read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/board":
                self._json(200, board_json(app.get_board()))
            elif path in STATIC:
                name, content_type = STATIC[path]
                self._send(200, (WEB / name).read_bytes(), content_type)
            else:
                self._json(404, {"error": "not found"})

        def _write(self) -> None:
            origin = self.headers.get("Origin")
            if self.headers.get("X-Requested-With") != "season" or (origin and origin not in allowed_origins):
                self._json(403, {"error": "forbidden"})
                return
            route = _route(self.command, self.path.split("?", 1)[0])
            if route is None:
                self._json(404, {"error": "not found"})
                return
            handler, m = route
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if length > MAX_BODY:
                    raise InvalidInput("request too large")
                body = json.loads(self.rfile.read(length) or b"{}") if length else {}
                if not isinstance(body, dict):
                    raise InvalidInput("body must be a JSON object")
                result = handler(app, m, body)
                reply = result if isinstance(result, Reply) else None
            except (InvalidInput, ValueError) as exc:
                self._json(400, {"error": str(exc)})
                return
            except NotFound as exc:
                self._json(404, {"error": str(exc)})
                return
            self._json(200, board_json(app.get_board(), reply))

        do_POST = do_PUT = do_DELETE = _write

    return RequestHandler


def serve(app: App) -> None:
    server = ThreadingHTTPServer((app.settings.host, app.settings.port), make_handler(app))
    server.daemon_threads = True
    server.serve_forever()
