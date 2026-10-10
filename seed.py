"""Load the plan into the database.  Usage: uv run seed.py [--allow-example]

Reads `plan.py` (yours, git-ignored). Without it, a fresh setup falls back to
`plan.example.py`; when the board already holds a plan, the example is refused so
placeholder weeks never overwrite real ones.

Re-running never touches checked boxes, tasks added on the board, or types changed
by hand.
"""

import sqlite3
import sys
from pathlib import Path

from season.application.plan import Plan

HERE = Path(__file__).resolve().parent
EXAMPLE = "plan.example.py"


def load_plan(allow_example: bool = False) -> tuple[Plan, str]:
    """Execute the first plan file found and hand back its PLAN. Kept out of `import`
    because a file named plan.py would otherwise be shadowed by the season.plan logic."""
    for name in ("plan.py", EXAMPLE):
        path = HERE / name
        if not path.is_file():
            continue
        if name == EXAMPLE and not allow_example:
            raise SystemExit(_example_message())
        namespace: dict = {"__file__": str(path), "__name__": "plan"}
        exec(compile(path.read_text(), str(path), "exec"), namespace)
        note = name if name == "plan.py" else f"{name} (example — run `cp {EXAMPLE} plan.py` to make it yours)"
        return namespace["PLAN"], note
    sys.exit(f"No plan found. Copy the example and edit it:\n    cp {EXAMPLE} plan.py\n"
             "then run `uv run seed.py` again.")


def plan_file_exists() -> bool:
    return (HERE / "plan.py").is_file()


def _weeks_in(db_path: Path) -> int:
    """Weeks already in the database, read-only, so a real plan is never overwritten."""
    if not db_path.is_file():
        return 0
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return 0
    try:
        return con.execute("SELECT COUNT(*) FROM weeks").fetchone()[0]
    except sqlite3.DatabaseError:
        return 0
    finally:
        con.close()


def _example_message() -> str:
    from season.config import load_settings
    weeks = _weeks_in(load_settings().db_path)
    if not weeks:
        return ""          # nothing to protect: a fresh board may use the example
    return (f"No plan.py, and the board already holds a plan ({weeks} weeks).\n"
            f"Refusing to replace it with placeholder weeks from {EXAMPLE}.\n"
            "Point the board at your own plan first (`cp <your backup> plan.py`).\n"
            "To use the example on purpose anyway: uv run seed.py --allow-example")


if __name__ == "__main__":
    from season.config import load_settings
    from season.container import build_app
    from season.interfaces.cli.remind import summary

    settings = load_settings()
    has_own_plan = plan_file_exists()
    message = "" if has_own_plan else _example_message()
    if message and "--allow-example" not in sys.argv:
        sys.exit(message)
    plan, source = load_plan(allow_example=not has_own_plan)

    app = build_app(settings)
    app.seed_plan(plan)
    board = app.get_board()
    tasks = sum(len(w.tasks) for w in board.weeks)
    print(f"{settings.db_path}: weeks={len(board.weeks)} tasks={tasks} "
          f"types={len(board.categories)} events={len(board.events)} problems={len(board.problems.problems)}")
    print(f"loaded from {source}")
    print(summary(app.get_week_status()))
