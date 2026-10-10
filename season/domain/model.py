"""Domain model for the season board.

Pure Python: no I/O, no frameworks. Every other layer depends on this one,
this one depends on nothing.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import date
from enum import StrEnum

from .errors import InvalidInput

OTHER = "other"
"""Fallback category. Always exists; anything unclear lands here."""

PROBLEM_LIST_TASK_KEY = "lc"
"""Planned task whose sessions walk through the LeetCode problem list."""

PAGES_TARGET = 100
MAX_TASK_TEXT = 160
MAX_NOTE = 500
MAX_CATEGORY_LABEL = 32
MAX_CATEGORY_DESCRIPTION = 200


class AssignedBy(StrEnum):
    """Who decided a task's category."""

    PLAN = "plan"          # written in the season plan
    JEV = "jev"            # classifier was confident
    FALLBACK = "fallback"  # classifier unsure or unavailable -> OTHER
    MANUAL = "manual"      # you picked it

    @property
    def is_automatic(self) -> bool:
        return self in (AssignedBy.JEV, AssignedBy.FALLBACK)


# ── categories ─────────────────────────────────────────────────────────────
_NON_WORD = re.compile(r"[^\w]+")


@dataclass(frozen=True, slots=True)
class Category:
    key: str
    label: str
    description: str
    builtin: bool = False

    @staticmethod
    def key_from_label(label: str) -> str:
        key = _NON_WORD.sub("-", label.strip().lower()).strip("-_")
        if not key:
            raise InvalidInput("type name needs at least one letter or number")
        return key[:MAX_CATEGORY_LABEL]

    @classmethod
    def create(cls, label: str, description: str) -> Category:
        label, description = label.strip(), description.strip()
        if not label:
            raise InvalidInput("type name is empty")
        if len(label) > MAX_CATEGORY_LABEL:
            raise InvalidInput(f"type name is longer than {MAX_CATEGORY_LABEL} characters")
        if not description:
            raise InvalidInput("say what belongs in this type, so tasks can be sorted into it")
        if len(description) > MAX_CATEGORY_DESCRIPTION:
            raise InvalidInput(f"description is longer than {MAX_CATEGORY_DESCRIPTION} characters")
        return cls(cls.key_from_label(label), label, description)


@dataclass(frozen=True, slots=True)
class CategoryAssignment:
    category: str
    assigned_by: AssignedBy
    confidence: float | None = None


# ── tasks and sessions ─────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class SessionMark:
    """One checked box: the day it was done, the problem if it was LeetCode, and an optional note."""

    done_on: date
    problem: int | None = None
    note: str | None = None


def clean_note(note: str | None) -> str | None:
    """Notes are optional. Blank means no note."""
    if note is None:
        return None
    note = note.strip()
    if not note:
        return None
    if len(note) > MAX_NOTE:
        raise InvalidInput(f"note is longer than {MAX_NOTE} characters")
    return note


def clean_task_text(text: str) -> str:
    text = " ".join(text.split())
    if not text:
        raise InvalidInput("task text is empty")
    if len(text) > MAX_TASK_TEXT:
        raise InvalidInput(f"task text is longer than {MAX_TASK_TEXT} characters")
    return text


@dataclass(frozen=True, slots=True)
class Task:
    id: int
    week_start: date
    key: str
    text: str
    category: str
    assigned_by: AssignedBy
    confidence: float | None
    sessions: int
    hours_each: float
    position: int
    user_added: bool
    marks: Mapping[int, SessionMark] = field(default_factory=dict)

    @classmethod
    def new_user_task(cls, week_start: date, key: str, text: str,
                      assignment: CategoryAssignment, position: int) -> Task:
        return cls(id=0, week_start=week_start, key=key, text=clean_task_text(text),
                   category=assignment.category, assigned_by=assignment.assigned_by,
                   confidence=assignment.confidence, sessions=1, hours_each=0.0,
                   position=position, user_added=True)

    @property
    def slots(self) -> list[SessionMark | None]:
        return [self.marks.get(i) for i in range(self.sessions)]

    @property
    def is_done(self) -> bool:
        return self.sessions > 0 and all(self.slots)

    @property
    def hours(self) -> float:
        return self.sessions * self.hours_each

    @property
    def tracks_problem_list(self) -> bool:
        return self.key == PROBLEM_LIST_TASK_KEY and not self.user_added

    def require_slot(self, slot: int) -> None:
        if not 0 <= slot < self.sessions:
            raise InvalidInput(f"slot {slot} does not exist on this task")

    def with_assignment(self, a: CategoryAssignment) -> Task:
        return replace(self, category=a.category, assigned_by=a.assigned_by, confidence=a.confidence)


# ── weeks, events, problems ────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class Week:
    start: date
    end: date
    label: str
    glance: str
    tasks: tuple[Task, ...] = ()

    @property
    def hours(self) -> float:
        return sum(t.hours for t in self.tasks)

    def contains(self, day: date) -> bool:
        return self.start <= day <= self.end


@dataclass(frozen=True, slots=True)
class Event:
    day: date
    text: str
    kind: str = ""


@dataclass(frozen=True, slots=True)
class Problem:
    number: int
    title: str


@dataclass(frozen=True, slots=True)
class ProblemQueue:
    """Ordered problem list and how far through it you are.

    position == len(problems) means the list is finished.
    """

    problems: tuple[Problem, ...]
    position: int = 0

    def __post_init__(self) -> None:
        if not 0 <= self.position <= len(self.problems):
            object.__setattr__(self, "position", max(0, min(self.position, len(self.problems))))

    @property
    def current(self) -> Problem | None:
        return self.problems[self.position] if self.position < len(self.problems) else None

    def advanced(self) -> ProblemQueue:
        return replace(self, position=min(self.position + 1, len(self.problems)))

    def rewound_for(self, number: int) -> ProblemQueue:
        """Undo an advance, but only if `number` was the problem just completed."""
        if self.position > 0 and self.problems[self.position - 1].number == number:
            return replace(self, position=self.position - 1)
        return self

    def advanced_past(self, number: int) -> ProblemQueue:
        """Redo an advance, but only if `number` is the problem you are on."""
        if self.current is not None and self.current.number == number:
            return self.advanced()
        return self


def check_pages(pages: int | None) -> int | None:
    if pages is None:
        return None
    if isinstance(pages, bool) or not isinstance(pages, int) or not 0 <= pages <= PAGES_TARGET:
        raise InvalidInput(f"pages must be a whole number from 0 to {PAGES_TARGET}")
    return pages


@dataclass(frozen=True, slots=True)
class Board:
    today: date
    weeks: tuple[Week, ...]
    events: tuple[Event, ...]
    categories: tuple[Category, ...]
    problems: ProblemQueue
    pages: int | None
    pages_target: int = PAGES_TARGET

    def week_of(self, day: date) -> Week | None:
        if not self.weeks:
            return None
        for w in self.weeks:
            if w.contains(day):
                return w
        return self.weeks[0] if day < self.weeks[0].start else self.weeks[-1]
