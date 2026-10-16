"""Use cases: everything the board can do, one class per action.

Each use case depends only on ports and the domain. Network calls (the
classifier) happen outside database transactions.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from season.domain.errors import InvalidInput, NotFound
from season.domain.model import (
    OTHER,
    AssignedBy,
    Board,
    Category,
    CategoryAssignment,
    Event,
    Problem,
    SessionMark,
    Task,
    Week,
    check_client_key,
    check_pages,
    clean_note,
    clean_task_text,
    parse_size,
)

from .plan import Plan
from .ports import Classifier, ClassifierUnavailable, Clock, Prediction, UnitOfWorkFactory


# ── classification policy ──────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class ClassificationPolicy:
    """Turns a raw prediction into a category. Unsure means OTHER."""

    min_probability: float = 0.5

    def decide(self, prediction: Prediction, categories: Sequence[Category]) -> CategoryAssignment:
        known = {c.key for c in categories}
        if prediction.category not in known or prediction.probability < self.min_probability:
            return CategoryAssignment(OTHER, AssignedBy.FALLBACK, prediction.probability)
        return CategoryAssignment(prediction.category, AssignedBy.JEV, prediction.probability)


def _classify(classifier: Classifier, policy: ClassificationPolicy,
              text: str, categories: Sequence[Category]) -> CategoryAssignment:
    try:
        prediction = classifier.predict(text, categories)
    except ClassifierUnavailable:
        return CategoryAssignment(OTHER, AssignedBy.FALLBACK, None)
    return policy.decide(prediction, categories)


# ── reads ──────────────────────────────────────────────────────────────────
class GetBoard:
    def __init__(self, uow: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow, self._clock = uow, clock

    def __call__(self) -> Board:
        with self._uow() as u:
            return Board(
                today=self._clock.today(),
                weeks=tuple(u.weeks.all()),
                events=tuple(u.events.all()),
                categories=tuple(u.categories.all()),
                problems=u.problems.queue(),
                pages=u.settings.pages(),
            )


@dataclass(frozen=True, slots=True)
class WeekStatus:
    today: date
    week: Week
    today_events: tuple[Event, ...]
    done_by_category: dict[str, int]
    pages: int | None


class GetWeekStatus:
    def __init__(self, get_board: GetBoard) -> None:
        self._get_board = get_board

    def __call__(self) -> WeekStatus:
        board = self._get_board()
        week = board.week_of(board.today)
        if week is None:
            raise NotFound("no weeks in the plan")
        done: dict[str, int] = {}
        for t in week.tasks:
            done[t.category] = done.get(t.category, 0) + sum(1 for s in t.slots if s)
        return WeekStatus(board.today, week, tuple(e for e in board.events if e.day == board.today),
                          done, board.pages)


# ── sessions ───────────────────────────────────────────────────────────────
class MarkSession:
    """Check one box. LeetCode boxes record the problem and advance the list."""

    def __init__(self, uow: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow, self._clock = uow, clock

    def __call__(self, task_id: int, slot: int, done_on: date | None = None) -> None:
        """done_on: the day it was done, when that differs from today (a phone syncing later)."""
        with self._uow() as u:
            task = u.tasks.get(task_id)
            task.require_slot(slot)
            if task.marks.get(slot):
                return
            problem = None
            if task.tracks_problem_list:
                queue = u.problems.queue()
                if queue.current:
                    problem = queue.current.number
                    u.problems.save_position(queue.advanced().position)
            u.tasks.set_mark(task_id, slot, SessionMark(done_on or self._clock.today(), problem))


class UnmarkSession:
    """Uncheck one box. Returns what was removed so the caller can offer Undo."""

    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def __call__(self, task_id: int, slot: int) -> SessionMark | None:
        with self._uow() as u:
            task = u.tasks.get(task_id)
            task.require_slot(slot)
            mark = task.marks.get(slot)
            if mark is None:
                return None
            if mark.problem is not None:
                u.problems.save_position(u.problems.queue().rewound_for(mark.problem).position)
            u.tasks.clear_mark(task_id, slot)
            return mark


class RestoreSession:
    """Undo an uncheck: put the box back with its original date, note and problem."""

    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def __call__(self, task_id: int, slot: int, mark: SessionMark) -> None:
        mark = SessionMark(mark.done_on, mark.problem, clean_note(mark.note))
        with self._uow() as u:
            task = u.tasks.get(task_id)
            task.require_slot(slot)
            if task.marks.get(slot):
                raise InvalidInput("that box is already checked")
            if mark.problem is not None and task.tracks_problem_list:
                u.problems.save_position(u.problems.queue().advanced_past(mark.problem).position)
            u.tasks.set_mark(task_id, slot, mark)


class SetSessionNote:
    """Add, change or clear the note on a checked box."""

    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def __call__(self, task_id: int, slot: int, note: str | None) -> None:
        note = clean_note(note)
        with self._uow() as u:
            task = u.tasks.get(task_id)
            task.require_slot(slot)
            if task.marks.get(slot) is None:
                raise InvalidInput("check the box before adding a note")
            u.tasks.set_note(task_id, slot, note)


class SkipProblem:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def __call__(self) -> None:
        with self._uow() as u:
            u.problems.save_position(u.problems.queue().advanced().position)


# ── tasks ──────────────────────────────────────────────────────────────────
class AddTask:
    """Add a task to a week; Jev picks its category, OTHER if unsure."""

    def __init__(self, uow: UnitOfWorkFactory, classifier: Classifier, policy: ClassificationPolicy) -> None:
        self._uow, self._classifier, self._policy = uow, classifier, policy

    def __call__(self, week_start: date, text: str, sessions: int | None = None,
                 hours_each: float | None = None, client_key: str | None = None) -> Task:
        """Size comes from the arguments, else from a trailing "3x2h" in the text, else 1 box of 1h."""
        text, parsed_sessions, parsed_hours = parse_size(clean_task_text(text))
        sessions = sessions if sessions is not None else parsed_sessions
        hours_each = hours_each if hours_each is not None else parsed_hours
        size = {k: v for k, v in (("sessions", sessions), ("hours_each", hours_each)) if v is not None}
        Task.new_user_task(week_start, "check", text, CategoryAssignment(OTHER, AssignedBy.FALLBACK), 0,
                           **size)          # validate before spending a classifier call
        key = check_client_key(client_key) if client_key else "added-" + uuid.uuid4().hex[:8]
        with self._uow() as u:
            if not u.weeks.exists(week_start):
                raise NotFound(f"no week starting {week_start}")
            if client_key and (existing := u.tasks.find_by_key(key)):
                return existing           # the same phone task, sent again
            categories = u.categories.all()
        assignment = _classify(self._classifier, self._policy, text, categories)
        with self._uow() as u:
            if client_key and (existing := u.tasks.find_by_key(key)):
                return existing
            task = Task.new_user_task(week_start, key, text,
                                      assignment, u.tasks.next_position(week_start), **size)
            return u.tasks.add(task)


class ResizeTask:
    """Change how many boxes a task has and the hours per box. Works on planned tasks too;
    re-seeding the plan keeps a size you set by hand."""

    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def __call__(self, task_id: int, sessions: int, hours_each: float) -> Task:
        with self._uow() as u:
            task = u.tasks.get(task_id).resized(sessions, hours_each)
            u.tasks.resize(task_id, task.sessions, task.hours_each)
            return task


class RemoveTask:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def __call__(self, task_id: int) -> None:
        with self._uow() as u:
            if not u.tasks.get(task_id).user_added:
                raise InvalidInput("only tasks you added can be removed")
            u.tasks.remove(task_id)


class AssignCategory:
    """You pick the category by hand. Manual choices are never re-sorted."""

    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def __call__(self, task_id: int, category: str) -> None:
        with self._uow() as u:
            u.tasks.get(task_id)
            if not u.categories.exists(category):
                raise NotFound(f"no type called {category!r}")
            u.tasks.assign(task_id, CategoryAssignment(category, AssignedBy.MANUAL))


@dataclass(frozen=True, slots=True)
class CategoryCreated:
    category: Category
    moved: int


class CreateCategory:
    """Add a new type, optionally put a task in it, then re-sort tasks stuck in OTHER."""

    def __init__(self, uow: UnitOfWorkFactory, classifier: Classifier, policy: ClassificationPolicy) -> None:
        self._uow, self._classifier, self._policy = uow, classifier, policy

    def __call__(self, label: str, description: str, task_id: int | None = None) -> CategoryCreated:
        category = Category.create(label, description)
        with self._uow() as u:
            if u.categories.exists(category.key):
                raise InvalidInput(f"a type called {category.label!r} already exists")
            if task_id is not None:
                u.tasks.get(task_id)
            u.categories.add(category)
            if task_id is not None:
                u.tasks.assign(task_id, CategoryAssignment(category.key, AssignedBy.MANUAL))
            categories = u.categories.all()
            stuck = [t for t in u.tasks.automatic_in(OTHER) if t.id != task_id]

        moves = []
        for t in stuck:
            a = _classify(self._classifier, self._policy, t.text, categories)
            if a.category != OTHER:
                moves.append((t.id, a))
        if moves:
            with self._uow() as u:
                for tid, a in moves:
                    u.tasks.assign(tid, a)
        return CategoryCreated(category, len(moves))


# ── settings ───────────────────────────────────────────────────────────────
class SetPages:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def __call__(self, pages: int | None) -> None:
        pages = check_pages(pages)
        with self._uow() as u:
            u.settings.set_pages(pages)


# ── seeding ────────────────────────────────────────────────────────────────
class SeedPlan:
    """Load or refresh the season plan. Never touches checked boxes or tasks you added."""

    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def __call__(self, plan: Plan) -> None:
        if not any(c.key == OTHER for c in plan.categories):
            raise InvalidInput("the plan must define the 'other' category")
        with self._uow() as u:
            for pos, c in enumerate(plan.categories):
                u.categories.upsert_builtin(Category(c.key, c.label, c.description, builtin=True), pos)
            known = {c.key for c in u.categories.all()}
            for w in plan.weeks:
                end = w.start + timedelta(days=6)
                u.weeks.upsert(Week(w.start, end, f"{w.start.day} {w.start:%b} – {end.day} {end:%b}", w.glance))
                for pos, t in enumerate(w.tasks):
                    if t.category not in known:
                        raise InvalidInput(f"plan task {t.key!r} uses unknown type {t.category!r}")
                    u.tasks.upsert_planned(Task(
                        id=0, week_start=w.start, key=t.key, text=t.text, category=t.category,
                        assigned_by=AssignedBy.PLAN, confidence=None, sessions=t.sessions,
                        hours_each=t.hours_each, position=pos, user_added=False))
                u.tasks.remove_planned_except(w.start, [t.key for t in w.tasks])
            u.events.replace_all([Event(e.day, e.text, e.kind) for e in plan.events])
            if plan.problems:
                u.problems.replace_list([Problem(n, title) for n, title in plan.problems])
