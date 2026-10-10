"""Shared test helpers: temp database, fixed clock, scripted classifier, small plan."""

import tempfile
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from season.adapters.system import SilentNotifier
from season.application.plan import Plan, PlanCategory, PlanEvent, PlanTask, PlanWeek
from season.application.ports import ClassifierUnavailable, Prediction
from season.config import Settings
from season.container import App, build_app
from season.domain.model import Category

MONDAY = date(2026, 10, 12)


class FixedClock:
    def __init__(self, day: date = MONDAY) -> None:
        self.day = day

    def today(self) -> date:
        return self.day


class ScriptedClassifier:
    """Answers from a {substring: (category, probability)} table; raises if `down`."""

    def __init__(self, table: dict[str, tuple[str, float]] | None = None, down: bool = False) -> None:
        self.table = table or {}
        self.down = down
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def predict(self, text: str, categories: Sequence[Category]) -> Prediction:
        self.calls.append((text, tuple(c.key for c in categories)))
        if self.down:
            raise ClassifierUnavailable("down")
        for needle, (cat, p) in self.table.items():
            if needle in text.lower() and cat in {c.key for c in categories}:
                return Prediction(cat, p, p)
        return Prediction("other", 0.9, 0.9)


PLAN = Plan(
    categories=(
        PlanCategory("thesis", "thesis", "Thesis writing"),
        PlanCategory("leetcode", "leetcode", "Coding practice"),
        PlanCategory("other", "other", "Anything else"),
    ),
    weeks=(
        PlanWeek(MONDAY, "first week", (PlanTask("thesis", "thesis", "Thesis", 3, 2),
                                         PlanTask("lc", "leetcode", "Top Interview 150", 2, 1))),
        PlanWeek(date(2026, 10, 19), "second week", (PlanTask("thesis", "thesis", "Thesis", 2, 2),)),
    ),
    events=(PlanEvent(date(2026, 10, 13), "Lab"),),
    problems=((117, "Next Right Pointers II"), (114, "Flatten"), (112, "Path sum")),
)


def make_app(classifier=None, clock=None, port: int = 0) -> tuple[App, tempfile.TemporaryDirectory]:
    tmp = tempfile.TemporaryDirectory()
    settings = Settings(home=Path(tmp.name), db_path=Path(tmp.name) / "test.db", host="127.0.0.1", port=port,
                        typesafe_api_key=None, typesafe_model="jev-latest", context=None, min_probability=0.5)
    app = build_app(settings, classifier=classifier or ScriptedClassifier(), clock=clock or FixedClock(),
                    notifier=SilentNotifier())
    app.seed_plan(PLAN)
    return app, tmp


def task(app: App, week: int, key: str):
    return next(t for t in app.get_board().weeks[week].tasks if t.key == key)
