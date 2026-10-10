"""Input DTOs for loading a season plan. Plain data, no behaviour."""

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True, slots=True)
class PlanCategory:
    key: str
    label: str
    description: str


@dataclass(frozen=True, slots=True)
class PlanTask:
    key: str
    category: str
    text: str
    sessions: int
    hours_each: float


@dataclass(frozen=True, slots=True)
class PlanWeek:
    start: date
    glance: str
    tasks: tuple[PlanTask, ...]


@dataclass(frozen=True, slots=True)
class PlanEvent:
    day: date
    text: str
    kind: str = ""


@dataclass(frozen=True, slots=True)
class Plan:
    categories: tuple[PlanCategory, ...]
    weeks: tuple[PlanWeek, ...]
    events: tuple[PlanEvent, ...] = ()
    problems: tuple[tuple[int, str], ...] = field(default=())
