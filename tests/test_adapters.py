import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import httpx2
from typesafe_sdk import TypeSafeClient

from season.adapters.jev_classifier import JevClassifier
from season.adapters.sqlite_store import SCHEMA_VERSION, SqliteDatabase
from season.application.ports import ClassifierUnavailable
from season.domain.model import Category

CATS = (Category("thesis", "thesis", "Thesis writing"), Category("other", "other", "Anything else"))


def _client(handler) -> TypeSafeClient:
    return TypeSafeClient(api_key="test-key", transport=httpx2.MockTransport(handler), retry=None)


class JevClassifierTest(unittest.TestCase):
    def test_sends_choice_and_reads_answer(self):
        seen = {}

        def handler(request):
            seen["body"] = json.loads(request.content)
            seen["auth"] = request.headers["authorization"]
            return httpx2.Response(200, json={"model": "jev-1.13.0", "answers": {"category": {
                "type": "choice", "choice": "thesis", "confidence": 0.9,
                "probabilities": {"thesis": 0.95, "other": 0.05}}}, "usage": {"input_tokens": 1, "output_tokens": 1}})

        p = JevClassifier("test-key", client=_client(handler)).predict("Draft intro", CATS)
        self.assertEqual((p.category, p.probability, p.confidence), ("thesis", 0.95, 0.9))
        q = seen["body"]["questions"]["category"]
        self.assertEqual((q["type"], set(q["criteria"])), ("choice", {"thesis", "other"}))
        self.assertEqual(seen["body"]["state"], {"task": "Draft intro"})
        self.assertEqual(seen["auth"], "Bearer test-key")

    def test_api_error_becomes_unavailable_without_leaking_key(self):
        def handler(request):
            return httpx2.Response(401, json={"error": "bad key"})

        with self.assertRaises(ClassifierUnavailable) as ctx:
            JevClassifier("test-key", client=_client(handler)).predict("x", CATS)
        self.assertNotIn("test-key", str(ctx.exception))

    def test_context_is_sent_when_configured(self):
        seen = {}

        def handler(request):
            seen["body"] = json.loads(request.content)
            return httpx2.Response(200, json={"model": "jev-1.13.0", "answers": {"category": {
                "type": "choice", "choice": "thesis", "confidence": 0.9,
                "probabilities": {"thesis": 0.95, "other": 0.05}}}, "usage": {"input_tokens": 1, "output_tokens": 1}})

        JevClassifier("k", context="  a student writing a thesis  ",
                      client=_client(handler)).predict("Draft intro", CATS)
        instructions = seen["body"]["questions"]["category"]["instructions"]
        self.assertTrue(instructions.startswith("a student writing a thesis"))
        JevClassifier("k", client=_client(handler)).predict("Draft intro", CATS)
        self.assertNotIn("student", seen["body"]["questions"]["category"]["instructions"])


V0 = """
CREATE TABLE weeks (start TEXT PRIMARY KEY, end TEXT NOT NULL, label TEXT NOT NULL, glance TEXT NOT NULL DEFAULT '');
CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, week TEXT NOT NULL REFERENCES weeks(start) ON DELETE CASCADE,
  key TEXT NOT NULL, tag TEXT NOT NULL, text TEXT NOT NULL, sessions INTEGER NOT NULL DEFAULT 1,
  each_h REAL NOT NULL DEFAULT 0, position INTEGER NOT NULL DEFAULT 0, added INTEGER NOT NULL DEFAULT 0,
  UNIQUE (week, key));
CREATE TABLE sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER NOT NULL REFERENCES tasks(id)
  ON DELETE CASCADE, slot INTEGER NOT NULL, done_on TEXT NOT NULL, lc INTEGER, UNIQUE (task_id, slot));
CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL, text TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT '');
CREATE TABLE lc_problems (pos INTEGER PRIMARY KEY, num INTEGER NOT NULL, title TEXT NOT NULL);
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT INTO weeks VALUES ('2026-10-12', '2026-10-18', '12 Oct – 18 Oct', '');
INSERT INTO tasks VALUES (1, '2026-10-12', 'lc', 'leetcode', 'Top Interview 150', 3, 1, 0, 0);
INSERT INTO tasks VALUES (2, '2026-10-12', 'added-x', 'network', 'Call Kenji', 1, 0, 1, 1);
INSERT INTO sessions VALUES (1, 1, 0, '2026-10-12', 117);
INSERT INTO lc_problems VALUES (0, 117, 'a'), (1, 114, 'b');
INSERT INTO settings VALUES ('lc_pos', '1'), ('pages', '12');
"""


class SqliteMigrationTest(unittest.TestCase):
    def test_v0_file_migrates_without_losing_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "old.db"
            con = sqlite3.connect(path)
            con.executescript(V0)
            con.close()

            db = SqliteDatabase(path)
            db.migrate()
            db.migrate()  # idempotent

            with db.unit_of_work() as u:
                tasks = u.weeks.all()[0].tasks
                self.assertEqual([t.category for t in tasks], ["leetcode", "network"])
                self.assertEqual(tasks[0].slots[0].problem, 117)
                self.assertEqual(tasks[1].assigned_by, "manual")
                self.assertEqual(u.problems.queue().current.number, 114)
                self.assertEqual(u.settings.pages(), 12)
                self.assertTrue(u.categories.exists("other"))
            raw = sqlite3.connect(path)
            self.assertEqual(raw.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
            self.assertEqual(raw.execute("PRAGMA foreign_key_check").fetchall(), [])
            raw.close()

    def test_v1_file_gains_notes_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "v1.db"
            con = sqlite3.connect(path)
            con.executescript(V0)
            con.close()
            db = SqliteDatabase(path)
            db.migrate()
            raw = sqlite3.connect(path)   # make it look like a v1 file
            raw.executescript("ALTER TABLE sessions DROP COLUMN note; PRAGMA user_version = 1;")
            raw.close()
            db.migrate()
            with db.unit_of_work() as u:
                mark = u.weeks.all()[0].tasks[0].slots[0]
                self.assertEqual((mark.problem, mark.note), (117, None))
                u.tasks.set_note(1, 0, "two pointers")
            with db.unit_of_work() as u:
                self.assertEqual(u.weeks.all()[0].tasks[0].slots[0].note, "two pointers")

    def test_v2_file_gains_resized_column_and_keeps_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "v2.db"
            con = sqlite3.connect(path)
            con.executescript(V0)
            con.close()
            db = SqliteDatabase(path)
            db.migrate()
            raw = sqlite3.connect(path)   # make it look like a v2 file
            raw.executescript("ALTER TABLE tasks DROP COLUMN resized; PRAGMA user_version = 2;")
            raw.close()
            db.migrate()
            with db.unit_of_work() as u:
                self.assertEqual(u.weeks.all()[0].tasks[0].slots[0].problem, 117)
                u.tasks.resize(1, 4, 1.5)
            with db.unit_of_work() as u:
                t = u.weeks.all()[0].tasks[0]
                self.assertEqual((t.sessions, t.hours_each), (4, 1.5))

    def test_unit_of_work_rolls_back_on_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = SqliteDatabase(Path(tmp) / "x.db")
            db.migrate()
            with self.assertRaises(RuntimeError):
                with db.unit_of_work() as u:
                    u.settings.set_pages(50)
                    raise RuntimeError("boom")
            with db.unit_of_work() as u:
                self.assertIsNone(u.settings.pages())


if __name__ == "__main__":
    unittest.main()
