import json
import unittest
from datetime import date

from season.application import sync as s
from season.domain.model import OTHER

from .support import MONDAY, FixedClock, ScriptedClassifier, make_app, task


def ids():
    n = 0
    while True:
        n += 1
        yield f"op-{n:08d}"


class SyncTest(unittest.TestCase):
    def setUp(self):
        self.clock = FixedClock(date(2026, 10, 16))
        self.app, self.tmp = make_app(ScriptedClassifier({"papers": ("thesis", 0.9)}), clock=self.clock)
        self.ids = ids()

    def tearDown(self):
        self.tmp.cleanup()

    def op(self, cls, *args, **kw):
        return cls(next(self.ids), *args, **kw)

    def test_offline_tick_keeps_its_own_day_and_note(self):
        thesis = task(self.app, 0, "thesis").id
        result = self.app.apply_sync([
            self.op(s.Mark, thesis, 0, date(2026, 10, 13)),
            self.op(s.SetNote, thesis, 0, "on the train"),
        ])
        self.assertTrue(all(r.ok for r in result.results))
        mark = task(self.app, 0, "thesis").slots[0]
        self.assertEqual((mark.done_on, mark.note), (date(2026, 10, 13), "on the train"))

    def test_phone_task_is_classified_and_later_ops_find_it(self):
        result = self.app.apply_sync([
            self.op(s.Add, "a1b2c3d4-0001", MONDAY, "Read papers 3x2h"),
            self.op(s.Mark, "a1b2c3d4-0001", 2, date(2026, 10, 14)),
            self.op(s.Resize, "a1b2c3d4-0001", 4, 1.5),
        ])
        self.assertEqual([r.ok for r in result.results], [True, True, True])
        t = next(t for t in self.app.get_board().weeks[0].tasks if t.text == "Read papers")
        self.assertEqual((t.category, t.sessions, t.hours_each, t.slots[2].done_on),
                         ("thesis", 4, 1.5, date(2026, 10, 14)))

    def test_resending_the_same_queue_changes_nothing(self):
        thesis = task(self.app, 0, "thesis").id
        queue = [self.op(s.Add, "a1b2c3d4-0002", MONDAY, "Buy ski wax"), self.op(s.Skip),
                 self.op(s.Mark, thesis, 1, date(2026, 10, 15))]
        self.app.apply_sync(queue)
        before = self.app.get_board()
        again = self.app.apply_sync(queue)
        after = self.app.get_board()
        self.assertTrue(all(r.repeated for r in again.results))
        self.assertEqual(after.problems.position, before.problems.position)          # skip not applied twice
        self.assertEqual(sum(t.text == "Buy ski wax" for t in after.weeks[0].tasks), 1)

    def test_add_is_idempotent_even_under_a_new_op_id(self):
        self.app.apply_sync([self.op(s.Add, "a1b2c3d4-0003", MONDAY, "Call Kenji")])
        self.app.apply_sync([self.op(s.Add, "a1b2c3d4-0003", MONDAY, "Call Kenji")])
        self.assertEqual(sum(t.text == "Call Kenji" for t in self.app.get_board().weeks[0].tasks), 1)

    def test_stale_ops_fail_with_a_reason_and_the_rest_still_apply(self):
        thesis = task(self.app, 0, "thesis").id
        result = self.app.apply_sync([
            self.op(s.Mark, 99999, 0, date(2026, 10, 14)),                 # deleted on the Mac
            self.op(s.Mark, "never-added-0001", 0, date(2026, 10, 14)),    # its add never arrived
            self.op(s.Mark, thesis, 9, date(2026, 10, 14)),                # box that no longer exists
            self.op(s.Mark, thesis, 0, date(2026, 10, 14)),
        ])
        self.assertEqual([r.ok for r in result.results], [False, False, False, True])
        self.assertTrue(all(r.error for r in result.failed))
        self.assertIsNotNone(task(self.app, 0, "thesis").slots[0])

    def test_unmark_restore_category_pages_remove(self):
        thesis = task(self.app, 0, "thesis").id
        self.app.mark_session(thesis, 0)
        self.app.set_session_note(thesis, 0, "draft")
        result = self.app.apply_sync([
            self.op(s.Unmark, thesis, 0),
            self.op(s.Restore, thesis, 0, date(2026, 10, 12), None, "draft"),
            self.op(s.Assign, thesis, OTHER),
            self.op(s.SetPages, 42),
            self.op(s.Add, "a1b2c3d4-0004", MONDAY, "Temp"),
            self.op(s.Remove, "a1b2c3d4-0004"),
            self.op(s.NewCategory, "Errands", "Paperwork and shopping"),
        ])
        self.assertTrue(all(r.ok for r in result.results), result.failed)
        board = self.app.get_board()
        t = task(self.app, 0, "thesis")
        self.assertEqual((t.slots[0].note, t.category, board.pages), ("draft", OTHER, 42))
        self.assertNotIn("Temp", [x.text for x in board.weeks[0].tasks])
        self.assertIn("errands", [c.key for c in board.categories])

    def test_offline_leetcode_tick_takes_the_current_problem(self):
        lc = task(self.app, 0, "lc").id
        self.app.apply_sync([self.op(s.Mark, lc, 0, date(2026, 10, 13))])
        self.assertEqual(task(self.app, 0, "lc").slots[0].problem, 117)
        self.assertEqual(self.app.get_board().problems.current.number, 114)


class SyncJsonTest(unittest.TestCase):
    def test_parse_and_reject(self):
        from season.domain.errors import InvalidInput
        from season.interfaces.http.sync_json import parse_ops
        ops = parse_ops({"ops": [
            {"id": "op-00000001", "kind": "mark", "task": 3, "slot": 0, "d": "2026-10-13"},
            {"id": "op-00000002", "kind": "add", "client_key": "abcd1234", "week": "2026-10-12", "text": "x",
             "sessions": 2, "hours": 1},
            {"id": "op-00000003", "kind": "pages", "pages": None},
        ]})
        self.assertEqual([type(o).__name__ for o in ops], ["Mark", "Add", "SetPages"])
        self.assertEqual(ops[1].hours, 1.0)
        for bad in ([{"id": "short", "kind": "skip"}], [{"id": "op-00000001", "kind": "explode"}],
                    [{"id": "op-00000001", "kind": "mark", "task": True, "slot": 0, "d": "2026-10-13"}],
                    [{"id": "op-00000001", "kind": "mark", "task": 1, "slot": 0, "d": "Tuesday"}], "nope"):
            with self.subTest(bad=bad), self.assertRaises(InvalidInput):
                parse_ops({"ops": bad})


class SyncHttpTest(unittest.TestCase):
    def test_round_trip_and_board_carries_upcoming_problems(self):
        import socket
        import threading
        import urllib.request
        from http.server import ThreadingHTTPServer

        from season.interfaces.http.server import make_handler
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        app, tmp = make_app(port=port)
        server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            thesis = task(app, 0, "thesis").id
            body = {"ops": [{"id": "op-http-0001", "kind": "mark", "task": thesis, "slot": 1, "d": "2026-10-13"},
                            {"id": "op-http-0002", "kind": "mark", "task": 99999, "slot": 0, "d": "2026-10-13"}]}
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/sync", method="POST",
                                         data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json", "X-Requested-With": "season"})
            with urllib.request.urlopen(req) as r:
                board = json.loads(r.read())
            self.assertEqual([x["ok"] for x in board["sync"]["results"]], [True, False])
            self.assertEqual(board["weeks"][0]["tasks"][0]["slots"][1]["d"], "2026-10-13")
            self.assertEqual([p["number"] for p in board["upcoming"]], [117, 114, 112])
        finally:
            server.shutdown()
            server.server_close()
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
