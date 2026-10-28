"""SQLite adapter: implements the repository ports and the unit of work.

Schema is versioned with PRAGMA user_version; `SqliteDatabase.migrate()`
brings any older file up to date without losing data.
"""

import json
import sqlite3
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Self

from season.domain.errors import InvalidInput, NotFound
from season.domain.model import (
    OTHER,
    AssignedBy,
    Category,
    CategoryAssignment,
    Event,
    Problem,
    ProblemQueue,
    SessionMark,
    Task,
    Week,
)

SCHEMA_VERSION = 5

_SCHEMA = """
CREATE TABLE IF NOT EXISTS weeks (
  start  TEXT PRIMARY KEY,
  end    TEXT NOT NULL,
  label  TEXT NOT NULL,
  glance TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS categories (
  key         TEXT PRIMARY KEY,
  label       TEXT NOT NULL,
  description TEXT NOT NULL,
  builtin     INTEGER NOT NULL DEFAULT 0,
  position    INTEGER NOT NULL DEFAULT 1000
);
CREATE TABLE IF NOT EXISTS tasks (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  week_start  TEXT NOT NULL REFERENCES weeks(start) ON DELETE CASCADE,
  key         TEXT NOT NULL,
  text        TEXT NOT NULL,
  category    TEXT NOT NULL REFERENCES categories(key),
  assigned_by TEXT NOT NULL,
  confidence  REAL,
  sessions    INTEGER NOT NULL DEFAULT 1,
  hours_each  REAL NOT NULL DEFAULT 0,
  position    INTEGER NOT NULL DEFAULT 0,
  user_added  INTEGER NOT NULL DEFAULT 0,
  resized     INTEGER NOT NULL DEFAULT 0,
  UNIQUE (week_start, key)
);
CREATE TABLE IF NOT EXISTS sessions (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  slot    INTEGER NOT NULL,
  done_on TEXT NOT NULL,
  problem INTEGER,
  note    TEXT,
  UNIQUE (task_id, slot)
);
CREATE TABLE IF NOT EXISTS events (
  id   INTEGER PRIMARY KEY AUTOINCREMENT,
  day  TEXT NOT NULL,
  text TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS problems (
  position INTEGER PRIMARY KEY,
  number   INTEGER NOT NULL,
  title    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS applied_ops (
  id         TEXT PRIMARY KEY,
  result     TEXT NOT NULL,
  applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pages_history (
  day   TEXT PRIMARY KEY,
  pages INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_done_on ON sessions(done_on);
CREATE INDEX IF NOT EXISTS events_day ON events(day);
CREATE INDEX IF NOT EXISTS tasks_category ON tasks(category);
"""

_OTHER_ROW = (OTHER, "other", "Anything that does not clearly fit one of the other types", 1, 9999)


def _statements(sql: str) -> list[str]:
    return [s.strip() for s in sql.split(";") if s.strip()]


def _run(con: sqlite3.Connection, sql: str) -> None:
    # Not executescript(): that silently COMMITs the open transaction.
    for statement in _statements(sql):
        con.execute(statement)


def _columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}


def _create(table: str, as_name: str) -> str:
    """The current CREATE statement for one table, optionally under another name."""
    for s in _statements(_SCHEMA):
        if s.startswith(f"CREATE TABLE IF NOT EXISTS {table} "):
            return s.replace(f"CREATE TABLE IF NOT EXISTS {table} ", f"CREATE TABLE {as_name} ", 1)
    raise KeyError(table)


def _migrate_v0_to_v1(con: sqlite3.Connection) -> None:
    """v0: tasks.tag / sessions.lc / lc_problems / lc_pos. Rebuild into v1 names."""
    con.execute(_create("categories", "IF NOT EXISTS categories"))
    con.execute(_create("problems", "IF NOT EXISTS problems"))
    con.execute(_create("tasks", "tasks_v1"))
    con.execute(_create("sessions", "sessions_v1"))
    con.execute("INSERT OR IGNORE INTO categories(key, label, description, builtin, position) VALUES(?,?,?,?,?)",
                _OTHER_ROW)
    for (tag,) in con.execute("SELECT DISTINCT tag FROM tasks").fetchall():
        con.execute("INSERT OR IGNORE INTO categories(key, label, description) VALUES(?, ?, ?)", (tag, tag, tag))
    con.execute(
        "INSERT INTO tasks_v1(id, week_start, key, text, category, assigned_by, confidence, sessions, "
        "hours_each, position, user_added) "
        "SELECT id, week, key, text, tag, CASE WHEN added = 1 THEN 'manual' ELSE 'plan' END, NULL, "
        "sessions, each_h, position, added FROM tasks"
    )
    con.execute("INSERT INTO sessions_v1(id, task_id, slot, done_on, problem) "
                "SELECT id, task_id, slot, done_on, lc FROM sessions")
    con.execute("DROP TABLE sessions")
    con.execute("DROP TABLE tasks")
    con.execute("ALTER TABLE tasks_v1 RENAME TO tasks")
    con.execute("ALTER TABLE sessions_v1 RENAME TO sessions")
    if "lc_problems" in {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
        con.execute("INSERT OR REPLACE INTO problems(position, number, title) SELECT pos, num, title FROM lc_problems")
        con.execute("DROP TABLE lc_problems")
    con.execute("UPDATE settings SET key = 'problem_position' WHERE key = 'lc_pos'")
    con.execute("DELETE FROM settings WHERE key = 'imported_progress_json'")


class SqliteDatabase:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        return con

    def migrate(self) -> None:
        con = self.connect()
        try:
            con.execute("PRAGMA journal_mode = WAL")
            version = con.execute("PRAGMA user_version").fetchone()[0]
            if version >= SCHEMA_VERSION:
                return
            con.execute("PRAGMA foreign_keys = OFF")
            con.execute("BEGIN")
            if "tag" in _columns(con, "tasks"):
                _migrate_v0_to_v1(con)
            _run(con, _SCHEMA)
            if "note" not in _columns(con, "sessions"):   # v1 -> v2
                con.execute("ALTER TABLE sessions ADD COLUMN note TEXT")
            if "resized" not in _columns(con, "tasks"):   # v2 -> v3
                con.execute("ALTER TABLE tasks ADD COLUMN resized INTEGER NOT NULL DEFAULT 0")
            con.execute("INSERT OR IGNORE INTO categories(key, label, description, builtin, position) "
                        "VALUES(?,?,?,?,?)", _OTHER_ROW)
            problems = con.execute("PRAGMA foreign_key_check").fetchall()
            if problems:
                con.execute("ROLLBACK")
                raise RuntimeError(f"migration left broken references: {problems[:3]}")
            con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            con.execute("COMMIT")
        finally:
            con.execute("PRAGMA foreign_keys = ON")
            con.close()

    def unit_of_work(self) -> SqliteUnitOfWork:
        return SqliteUnitOfWork(self)


# ── repositories ───────────────────────────────────────────────────────────
def _d(s: str) -> date:
    return date.fromisoformat(s)


class _Settings:
    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con

    def get(self, key: str, default=None):
        row = self._con.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def put(self, key: str, value) -> None:
        self._con.execute("INSERT INTO settings(key, value) VALUES(?, ?) "
                          "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, json.dumps(value)))

    def pages(self) -> int | None:
        return self.get("pages")

    def set_pages(self, pages: int | None, on: date) -> None:
        """Store the count, and keep one row per day so a stall is visible later."""
        self.put("pages", pages)
        if pages is not None:
            self._con.execute("INSERT INTO pages_history(day, pages) VALUES(?, ?) "
                              "ON CONFLICT(day) DO UPDATE SET pages = excluded.pages",
                              (on.isoformat(), pages))

    def pages_history(self) -> list[tuple[date, int]]:
        return [(_d(r["day"]), r["pages"])
                for r in self._con.execute("SELECT day, pages FROM pages_history ORDER BY day")]


class _Tasks:
    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con

    def _marks(self, task_ids: Sequence[int]) -> dict[int, dict[int, SessionMark]]:
        out: dict[int, dict[int, SessionMark]] = {i: {} for i in task_ids}
        if not task_ids:
            return out
        q = ",".join("?" * len(task_ids))
        for r in self._con.execute(
                f"SELECT task_id, slot, done_on, problem, note FROM sessions WHERE task_id IN ({q})", tuple(task_ids)):
            out[r["task_id"]][r["slot"]] = SessionMark(_d(r["done_on"]), r["problem"], r["note"])
        return out

    def _build(self, rows: Sequence[sqlite3.Row]) -> list[Task]:
        marks = self._marks([r["id"] for r in rows])
        return [Task(
            id=r["id"], week_start=_d(r["week_start"]), key=r["key"], text=r["text"], category=r["category"],
            assigned_by=AssignedBy(r["assigned_by"]), confidence=r["confidence"], sessions=r["sessions"],
            hours_each=r["hours_each"], position=r["position"], user_added=bool(r["user_added"]),
            marks=marks[r["id"]]) for r in rows]

    def in_week(self, start: str) -> list[Task]:
        return self._build(self._con.execute(
            "SELECT * FROM tasks WHERE week_start = ? ORDER BY position, id", (start,)).fetchall())

    def find_by_key(self, key: str) -> Task | None:
        rows = self._con.execute("SELECT * FROM tasks WHERE key = ? ORDER BY id LIMIT 1", (key,)).fetchall()
        return self._build(rows)[0] if rows else None

    def get(self, task_id: int) -> Task:
        rows = self._con.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchall()
        if not rows:
            raise NotFound(f"no task {task_id}")
        return self._build(rows)[0]

    def add(self, task: Task) -> Task:
        cur = self._con.execute(
            "INSERT INTO tasks(week_start, key, text, category, assigned_by, confidence, sessions, hours_each, "
            "position, user_added) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (task.week_start.isoformat(), task.key, task.text, task.category, task.assigned_by.value,
             task.confidence, task.sessions, task.hours_each, task.position, int(task.user_added)))
        return self.get(cur.lastrowid)

    def remove(self, task_id: int) -> None:
        self._con.execute("DELETE FROM tasks WHERE id = ?", (task_id,))

    def assign(self, task_id: int, a: CategoryAssignment) -> None:
        self._con.execute("UPDATE tasks SET category = ?, assigned_by = ?, confidence = ? WHERE id = ?",
                          (a.category, a.assigned_by.value, a.confidence, task_id))

    def set_mark(self, task_id: int, slot: int, mark: SessionMark) -> None:
        self._con.execute("INSERT INTO sessions(task_id, slot, done_on, problem, note) VALUES(?,?,?,?,?) "
                          "ON CONFLICT(task_id, slot) DO UPDATE SET done_on = excluded.done_on, "
                          "problem = excluded.problem, note = excluded.note",
                          (task_id, slot, mark.done_on.isoformat(), mark.problem, mark.note))

    def resize(self, task_id: int, sessions: int, hours_each: float) -> None:
        self._con.execute("UPDATE tasks SET sessions = ?, hours_each = ?, resized = 1 WHERE id = ?",
                          (sessions, hours_each, task_id))

    def set_note(self, task_id: int, slot: int, note: str | None) -> None:
        self._con.execute("UPDATE sessions SET note = ? WHERE task_id = ? AND slot = ?", (note, task_id, slot))

    def set_done_on(self, task_id: int, slot: int, done_on: date) -> None:
        self._con.execute("UPDATE sessions SET done_on = ? WHERE task_id = ? AND slot = ?",
                          (done_on.isoformat(), task_id, slot))

    def clear_mark(self, task_id: int, slot: int) -> None:
        self._con.execute("DELETE FROM sessions WHERE task_id = ? AND slot = ?", (task_id, slot))

    def next_position(self, week_start: date) -> int:
        return self._con.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM tasks WHERE week_start = ?",
                                 (week_start.isoformat(),)).fetchone()[0]

    def automatic_in(self, category: str) -> list[Task]:
        return self._build(self._con.execute(
            "SELECT * FROM tasks WHERE category = ? AND assigned_by IN (?, ?) ORDER BY id",
            (category, AssignedBy.JEV.value, AssignedBy.FALLBACK.value)).fetchall())

    def upsert_planned(self, task: Task) -> None:
        # A category you changed by hand survives re-seeding.
        self._con.execute(
            "INSERT INTO tasks(week_start, key, text, category, assigned_by, confidence, sessions, hours_each, "
            "position, user_added) VALUES(?,?,?,?,?,NULL,?,?,?,0) "
            "ON CONFLICT(week_start, key) DO UPDATE SET text = excluded.text, "
            "sessions = CASE WHEN tasks.resized THEN tasks.sessions ELSE excluded.sessions END, "
            "hours_each = CASE WHEN tasks.resized THEN tasks.hours_each ELSE excluded.hours_each END, "
            "position = excluded.position, "
            "category = CASE WHEN tasks.assigned_by = 'manual' THEN tasks.category ELSE excluded.category END",
            (task.week_start.isoformat(), task.key, task.text, task.category, AssignedBy.PLAN.value,
             task.sessions, task.hours_each, task.position))

    def remove_planned_except(self, week_start: date, keep_keys: Sequence[str]) -> None:
        q = ",".join("?" * len(keep_keys)) or "''"
        self._con.execute(f"DELETE FROM tasks WHERE week_start = ? AND user_added = 0 AND key NOT IN ({q})",
                          (week_start.isoformat(), *keep_keys))


class _Weeks:
    def __init__(self, con: sqlite3.Connection, tasks: _Tasks) -> None:
        self._con, self._tasks = con, tasks

    def all(self) -> list[Week]:
        return [Week(_d(r["start"]), _d(r["end"]), r["label"], r["glance"], tuple(self._tasks.in_week(r["start"])))
                for r in self._con.execute("SELECT * FROM weeks ORDER BY start")]

    def exists(self, start: date) -> bool:
        return self._con.execute("SELECT 1 FROM weeks WHERE start = ?", (start.isoformat(),)).fetchone() is not None

    def upsert(self, w: Week) -> None:
        self._con.execute("INSERT INTO weeks(start, end, label, glance) VALUES(?,?,?,?) "
                          "ON CONFLICT(start) DO UPDATE SET end = excluded.end, label = excluded.label, "
                          "glance = excluded.glance",
                          (w.start.isoformat(), w.end.isoformat(), w.label, w.glance))


class _Categories:
    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con

    def all(self) -> list[Category]:
        return [Category(r["key"], r["label"], r["description"], bool(r["builtin"]))
                for r in self._con.execute("SELECT * FROM categories ORDER BY position, label")]

    def exists(self, key: str) -> bool:
        return self._con.execute("SELECT 1 FROM categories WHERE key = ?", (key,)).fetchone() is not None

    def add(self, c: Category) -> None:
        try:
            self._con.execute("INSERT INTO categories(key, label, description, builtin, position) "
                              "VALUES(?, ?, ?, 0, (SELECT COALESCE(MAX(position), 0) + 1 FROM categories "
                              "WHERE key != ?))", (c.key, c.label, c.description, OTHER))
        except sqlite3.IntegrityError as exc:
            raise InvalidInput(f"a type called {c.label!r} already exists") from exc

    def upsert_builtin(self, c: Category, position: int) -> None:
        self._con.execute("INSERT INTO categories(key, label, description, builtin, position) VALUES(?,?,?,1,?) "
                          "ON CONFLICT(key) DO UPDATE SET label = excluded.label, "
                          "description = excluded.description, builtin = 1, position = excluded.position",
                          (c.key, c.label, c.description, position))


class _Events:
    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con

    def all(self) -> list[Event]:
        return [Event(_d(r["day"]), r["text"], r["kind"])
                for r in self._con.execute("SELECT day, text, kind FROM events ORDER BY day, id")]

    def replace_all(self, events: Sequence[Event]) -> None:
        self._con.execute("DELETE FROM events")
        self._con.executemany("INSERT INTO events(day, text, kind) VALUES(?,?,?)",
                              [(e.day.isoformat(), e.text, e.kind) for e in events])


class _Problems:
    def __init__(self, con: sqlite3.Connection, settings: _Settings) -> None:
        self._con, self._settings = con, settings

    def queue(self) -> ProblemQueue:
        problems = tuple(Problem(r["number"], r["title"])
                         for r in self._con.execute("SELECT number, title FROM problems ORDER BY position"))
        return ProblemQueue(problems, int(self._settings.get("problem_position", 0) or 0))

    def save_position(self, position: int) -> None:
        self._settings.put("problem_position", position)

    def replace_list(self, problems: Sequence[Problem]) -> None:
        self._con.execute("DELETE FROM problems")
        self._con.executemany("INSERT INTO problems(position, number, title) VALUES(?,?,?)",
                              [(i, p.number, p.title) for i, p in enumerate(problems)])


class _AppliedOps:
    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con

    def result(self, op_id: str) -> str | None:
        row = self._con.execute("SELECT result FROM applied_ops WHERE id = ?", (op_id,)).fetchone()
        return row["result"] if row else None

    def record(self, op_id: str, result: str) -> None:
        self._con.execute("INSERT OR IGNORE INTO applied_ops(id, result) VALUES(?, ?)", (op_id, result))


class SqliteUnitOfWork:
    def __init__(self, db: SqliteDatabase) -> None:
        self._db = db
        self._con: sqlite3.Connection | None = None

    def __enter__(self) -> Self:
        con = self._db.connect()
        con.execute("BEGIN IMMEDIATE")
        self._con = con
        settings = _Settings(con)
        self.settings = settings
        self.tasks = _Tasks(con)
        self.applied_ops = _AppliedOps(con)
        self.weeks = _Weeks(con, self.tasks)
        self.categories = _Categories(con)
        self.events = _Events(con)
        self.problems = _Problems(con, settings)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        con, self._con = self._con, None
        if con is None:
            return
        try:
            con.execute("ROLLBACK" if exc_type else "COMMIT")
        finally:
            con.close()
