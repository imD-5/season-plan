"""The shipped example plan must run, and must never replace a real plan by accident."""

import importlib.util
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location("seed_module", ROOT / "seed.py")
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)


class ExamplePlanTest(unittest.TestCase):
    def test_example_is_valid(self):
        from season.application.plan import Plan
        from season.domain.model import MAX_TASK_TEXT
        from season.interfaces.cli.remind import summary
        from tests.support import ScriptedClassifier, make_app

        spec = importlib.util.spec_from_file_location("planx", ROOT / "plan.example.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        plan = module.PLAN
        self.assertIsInstance(plan, Plan)
        self.assertGreaterEqual(len(plan.weeks), 1)
        self.assertTrue(any(c.key == "other" for c in plan.categories))
        for week in plan.weeks:
            self.assertTrue(week.glance, "every week needs a line for the board")
            for t in week.tasks:
                self.assertLessEqual(len(t.text), MAX_TASK_TEXT)
                self.assertIn(t.category, {c.key for c in plan.categories})
                self.assertIn(t.key, {"thesis", "slides", "practice", "network", "project", "admin"})
        # it must survive a real seeding
        app, tmp = make_app(ScriptedClassifier())
        with tmp:
            app.seed_plan(plan)
            board = app.get_board()
            # the example's own weeks must land; the board may hold weeks from the plan seeded before it
            self.assertLessEqual({w.start for w in plan.weeks}, {w.start for w in board.weeks})
            self.assertTrue(summary(app.get_week_status()))

    def test_example_is_refused_over_an_existing_plan(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "season.db"
            con = sqlite3.connect(db)
            con.execute("CREATE TABLE weeks (start TEXT PRIMARY KEY, end TEXT, label TEXT, glance TEXT)")
            con.execute("INSERT INTO weeks VALUES ('2026-10-12','2026-10-18','mine','')")
            con.commit()
            con.close()
            self.assertEqual(seed._weeks_in(db), 1)

    def test_plan_file_is_gitignored_not_the_example(self):
        import subprocess
        ignored = subprocess.run(["git", "check-ignore", "-q", "plan.py"], cwd=ROOT)
        self.assertEqual(ignored.returncode, 0, "plan.py must be git-ignored")
        tracked = subprocess.run(["git", "check-ignore", "-q", "plan.example.py"], cwd=ROOT)
        self.assertEqual(tracked.returncode, 1, "plan.example.py must not be ignored")


if __name__ == "__main__":
    unittest.main()
