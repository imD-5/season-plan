"""Pacing: are the boxes on the board enough to reach the deadline?

Pure Python, no I/O, no clock of its own.

The thesis is the only thing with a hard date, so pacing is about it: pages
written so far, pages still to write, the rate achieved so far, and the hours
the plan still holds. The point of the comparison is that a shortfall is a fact
about the *menu*, not about you: `sessions_short` says how many more boxes the
week would need to carry. Nothing here adds work; it only says whether the work
already written down is enough.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from .model import Board, Event, Task, Week

THESIS = "thesis"
"""Category whose boxes count as thesis work."""

DUE_KIND = "due"
"""Event kind that marks a hard deadline. The plan writes it; nothing guesses."""

DEFAULT_BOX_HOURS = 2.0
"""Hours assumed per box when the plan has no thesis boxes left to measure."""

STALL_DAYS = 14
"""Days without a page change before the pace line says the pages are stuck."""


class PaceStatus(StrEnum):
    DONE = "done"        # the target page count is reached
    OVERDUE = "overdue"  # the deadline has passed with pages still to write
    UNKNOWN = "unknown"  # no page count yet, or no rate to judge by
    SHORT = "short"      # the plan's remaining boxes buy fewer pages than are left
    OK = "ok"            # the plan's remaining boxes cover the pages left


def deadline_from(events: Sequence[Event], today: date) -> date | None:
    """The next `due` event; after it has passed, the most recent one, so it still shows."""
    due = [e.day for e in events if e.kind == DUE_KIND]
    if not due:
        return None
    upcoming = [d for d in due if d >= today]
    return min(upcoming) if upcoming else max(due)


def _thesis(week: Week) -> list[Task]:
    return [t for t in week.tasks if t.category == THESIS]


def _checked(task: Task) -> int:
    return sum(1 for s in task.slots if s)


def last_move(history: Sequence[tuple[date, int]]) -> date | None:
    """The day the page count last changed; with no change yet, the first day recorded.

    Pages that sit still are the quiet failure: the PDF keeps its count while the
    thesis does not grow, so the sync says nothing and the deadline slips unseen.
    """
    if not history:
        return None
    moved, previous = None, history[0][1]
    for day, pages in history:
        if pages != previous:
            moved, previous = day, pages
    return moved or history[0][0]


@dataclass(frozen=True, slots=True)
class Pace:
    """What the deadline needs, against what the plan holds."""

    today: date
    deadline: date
    pages: int | None
    target: int
    pages_left: int
    days_left: int
    weeks_left: float
    pages_per_week: float
    hours_done: float        # thesis hours already ticked off, all weeks
    hours_left: float        # thesis hours still unchecked in this week and later
    rate: float | None       # pages per thesis hour, measured from what is done
    hours_needed: float | None
    box_hours: float         # hours per box, to turn the gap into boxes
    sessions_short: int      # extra boxes the remaining weeks would need
    status: PaceStatus
    boxes_per_week: int = 0  # boxes a week that would hold the deadline at the measured rate
    moved_on: date | None = None   # the day the page count last changed
    stalled_days: int | None = None
    ticked_on: date | None = None  # the day a thesis box was last ticked

    @property
    def stalled(self) -> bool:
        """Nothing on the thesis for STALL_DAYS: no page change and no box ticked.

        A box ticked is thesis work even when it produces no page — research, analysis,
        reading. That is not a stall, so it must not raise the warning.
        """
        if self.stalled_days is None or self.pages_left <= 0 or self.stalled_days < STALL_DAYS:
            return False
        if self.ticked_on is not None and (self.today - self.ticked_on).days < STALL_DAYS:
            return False
        return True

    @property
    def wake(self) -> bool:
        """Worth saying out loud, even on a day the routine checks stay quiet."""
        return self.status is PaceStatus.SHORT or self.stalled

    @property
    def estimate(self) -> int | None:
        """Pages the booked hours buy at the measured rate."""
        if self.rate is None:
            return None
        return int(round(self.hours_left * self.rate))

    def line(self) -> str:
        """One line, for the board and the reminders. Same words in both places."""
        if self.status is PaceStatus.DONE:
            return f"{self.target} pp — done."
        if self.pages is None:
            return "No page count yet. Set pages on the board to see the pace."
        if self.status is PaceStatus.OVERDUE:
            return f"Deadline passed {-self.days_left} days ago, {self.pages} pp on the board."
        parts = [f"{self.pages_left} pp left"]
        if self.boxes_per_week:
            parts.append(f"{self.boxes_per_week} boxes/wk keeps {self.deadline:%d %b}")
        else:
            parts.append(f"need {self.pages_per_week:.1f} pp/wk")
        if self.status is PaceStatus.OK:
            parts.append(f"{self.hours_left:g}h booked")
        elif self.status is PaceStatus.SHORT:
            parts.append(f"{self.hours_left:g}h booked ≈ {self.estimate} pp")
            boxes = self.sessions_short
            parts.append(f"{boxes} box{'' if boxes == 1 else 'es'} short")
        if self.stalled:
            return f"pages stuck {self.stalled_days} days · " + " · ".join(parts)
        return " · ".join(parts)


def measure(board: Board, deadline: date, today: date | None = None) -> Pace:
    """Compare the pages still to write with the thesis boxes still on the board."""
    today = today or board.today
    target = board.pages_target
    pages = board.pages
    pages_left = 0 if pages is None else max(0, target - pages)
    days_left = (deadline - today).days
    weeks_left = max(0.0, days_left / 7)

    hours_done = sum(t.hours_each * _checked(t) for w in board.weeks for t in _thesis(w))
    # hours only count if they fall before the deadline: time after it cannot be spent on it
    open_weeks = [w for w in board.weeks if w.end >= today and w.start <= deadline]
    hours_left = sum(t.hours_each * (t.sessions - _checked(t)) for w in open_weeks for t in _thesis(w))
    sizes = sorted(t.hours_each for w in open_weeks for t in _thesis(w) if t.hours_each > 0)
    box_hours = sizes[len(sizes) // 2] if sizes else DEFAULT_BOX_HOURS

    rate = (pages / hours_done) if pages and hours_done > 0 else None
    hours_needed = (pages_left / rate) if rate else None
    pages_per_week = (pages_left / weeks_left) if weeks_left > 0 else 0.0

    if pages is None:
        status = PaceStatus.UNKNOWN
    elif pages_left == 0:
        status = PaceStatus.DONE
    elif days_left < 0:
        status = PaceStatus.OVERDUE
    elif hours_needed is None:
        status = PaceStatus.UNKNOWN
    elif hours_needed - hours_left > box_hours / 2:      # half a box of slack
        status = PaceStatus.SHORT
    else:
        status = PaceStatus.OK

    gap = (hours_needed - hours_left) if hours_needed is not None else 0.0
    sessions_short = max(0, math.ceil(gap / box_hours)) if status is PaceStatus.SHORT else 0

    moved_on = last_move(board.pages_history)
    stalled_days = (today - moved_on).days if moved_on is not None else None
    ticks = [s.done_on for w in board.weeks for t in _thesis(w) for s in t.slots if s]
    ticked_on = max(ticks) if ticks else None

    # the one number to hit each week: pages still needed per week, turned into boxes
    boxes_per_week = (math.ceil(pages_per_week / rate / box_hours)
                      if rate and box_hours and weeks_left > 0 else 0)

    return Pace(today=today, deadline=deadline, pages=pages, target=target, pages_left=pages_left,
                days_left=days_left, weeks_left=weeks_left, pages_per_week=pages_per_week,
                hours_done=hours_done, hours_left=hours_left, rate=rate, hours_needed=hours_needed,
                box_hours=box_hours, sessions_short=sessions_short, status=status,
                moved_on=moved_on, stalled_days=stalled_days, ticked_on=ticked_on,
                boxes_per_week=boxes_per_week)


def pace_for(board: Board, today: date | None = None) -> Pace | None:
    """Pace against the plan's own deadline, or None when the plan names no date."""
    today = today or board.today
    deadline = deadline_from(board.events, today)
    return None if deadline is None else measure(board, deadline, today)
