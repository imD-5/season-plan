import json
import socket
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from season.interfaces.http.server import make_handler

from .support import ScriptedClassifier, make_app, task


class HttpTest(unittest.TestCase):
    def setUp(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        self.app, self.tmp = make_app(ScriptedClassifier({"related work": ("thesis", 0.9), "wax": ("ski", 0.9)}),
                                      port=self.port)
        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), make_handler(self.app))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def call(self, method, path, body=None, headers=None):
        h = {"Content-Type": "application/json", "X-Requested-With": "season"}
        h.update(headers or {})
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method=method, headers=h,
                                     data=None if body is None else json.dumps(body).encode())
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            with e:
                return e.code, json.loads(e.read())

    def test_board_and_ui(self):
        status, board = self.call("GET", "/api/board")
        self.assertEqual(status, 200)
        self.assertEqual(board["problem"]["number"], 117)
        self.assertIn("other", [c["key"] for c in board["categories"]])
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/") as r:
            self.assertIn(b"Season board", r.read())

    def test_add_task_is_classified(self):
        status, board = self.call("POST", "/api/tasks", {"week": "2026-10-12", "text": "Draft related work"})
        self.assertEqual(status, 200)
        added = [t for t in board["weeks"][0]["tasks"] if t["user_added"]]
        self.assertEqual((added[0]["category"], added[0]["assigned_by"]), ("thesis", "jev"))

    def test_mark_and_unmark(self):
        tid = task(self.app, 0, "thesis").id
        _, board = self.call("POST", f"/api/tasks/{tid}/slots/0")
        self.assertIsNotNone(board["weeks"][0]["tasks"][0]["slots"][0])
        _, board = self.call("DELETE", f"/api/tasks/{tid}/slots/0")
        self.assertIsNone(board["weeks"][0]["tasks"][0]["slots"][0])

    def test_new_type_with_notice(self):
        self.call("POST", "/api/tasks", {"week": "2026-10-12", "text": "Buy ski wax"})
        status, board = self.call("POST", "/api/categories", {"label": "Ski", "description": "Ski trips"})
        self.assertEqual(status, 200)
        self.assertIn("Moved 1 task", board["notice"])

    def test_same_origin_writes_are_allowed(self):
        tid = task(self.app, 0, "thesis").id
        status, _ = self.call("POST", f"/api/tasks/{tid}/slots/0", headers={"Origin": f"http://127.0.0.1:{self.port}"})
        self.assertEqual(status, 200)

    def test_errors(self):
        self.assertEqual(self.call("POST", "/api/tasks/9999/slots/0")[0], 404)
        self.assertEqual(self.call("PUT", "/api/pages", {"pages": 500})[0], 400)
        self.assertEqual(self.call("POST", "/api/tasks", {"week": "nope", "text": "x"})[0], 400)
        self.assertEqual(self.call("POST", "/api/nowhere")[0], 404)

    def test_note_and_undo_over_http(self):
        tid = task(self.app, 0, "thesis").id
        base = f"/api/tasks/{tid}/slots/0"
        self.call("POST", base)
        status, board = self.call("PUT", base + "/note", {"note": "fixed fig 3"})
        self.assertEqual((status, board["weeks"][0]["tasks"][0]["slots"][0]["note"]), (200, "fixed fig 3"))
        _, board = self.call("DELETE", base)
        undo = board["undo"]
        self.assertEqual((undo["task_id"], undo["slot"], undo["note"]), (tid, 0, "fixed fig 3"))
        _, board = self.call("POST", base + "/restore", {k: undo[k] for k in ("d", "problem", "note")})
        self.assertEqual(board["weeks"][0]["tasks"][0]["slots"][0]["note"], "fixed fig 3")
        _, board = self.call("PUT", base + "/note", {"note": None})
        self.assertIsNone(board["weeks"][0]["tasks"][0]["slots"][0]["note"])
        self.assertEqual(self.call("PUT", base + "/note", {"note": 5})[0], 400)

    def test_task_size_over_http(self):
        _, board = self.call("POST", "/api/tasks", {"week": "2026-10-12", "text": "Read papers 3x2h"})
        added = [t for t in board["weeks"][0]["tasks"] if t["user_added"]][0]
        self.assertEqual((added["text"], added["sessions"], added["each"]), ("Read papers", 3, 2.0))
        status, board = self.call("PUT", f"/api/tasks/{added['id']}/size", {"sessions": 5, "hours": 1.5})
        got = [t for t in board["weeks"][0]["tasks"] if t["id"] == added["id"]][0]
        self.assertEqual((status, got["sessions"], got["each"], len(got["slots"])), (200, 5, 1.5, 5))
        self.call("POST", f"/api/tasks/{added['id']}/slots/3")
        _, board = self.call("GET", "/api/board")
        got = [t for t in board["weeks"][0]["tasks"] if t["id"] == added["id"]][0]
        self.assertEqual(got["min_sessions"], 4)
        self.assertEqual(self.call("PUT", f"/api/tasks/{added['id']}/size", {"sessions": 2, "hours": 1})[0], 400)
        self.assertEqual(self.call("PUT", f"/api/tasks/{added['id']}/size", {"sessions": 5})[0], 400)
        self.assertEqual(self.call("PUT", f"/api/tasks/{added['id']}/size", {"sessions": "5", "hours": 1})[0], 400)

    def test_cross_site_writes_are_refused(self):
        tid = task(self.app, 0, "thesis").id
        self.assertEqual(self.call("POST", f"/api/tasks/{tid}/slots/0", headers={"X-Requested-With": ""})[0], 403)
        self.assertEqual(self.call("POST", f"/api/tasks/{tid}/slots/0",
                                   headers={"Origin": "https://evil.example"})[0], 403)
        self.assertIsNone(task(self.app, 0, "thesis").slots[0])


if __name__ == "__main__":
    unittest.main()
