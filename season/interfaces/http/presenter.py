"""Turns domain objects into the JSON the board UI reads."""

from dataclasses import dataclass

from season.application.sync import SyncResult
from season.domain.model import Board, Category, SessionMark, Task, Week


@dataclass(frozen=True, slots=True)
class Undo:
    """Enough to put an unchecked box back exactly as it was."""

    task_id: int
    slot: int
    mark: SessionMark


@dataclass(frozen=True, slots=True)
class Reply:
    notice: str | None = None
    undo: Undo | None = None
    sync: SyncResult | None = None


UPCOMING = 60


def mark_json(m: SessionMark) -> dict:
    return {"d": m.done_on.isoformat(), "problem": m.problem, "note": m.note}


def _task(t: Task) -> dict:
    return {
        "id": t.id,
        "key": t.key,
        "text": t.text,
        "category": t.category,
        "assigned_by": t.assigned_by.value,
        "confidence": t.confidence,
        "sessions": t.sessions,
        "each": t.hours_each,
        "user_added": t.user_added,
        "problem_list": t.tracks_problem_list,
        "min_sessions": max(1, t.checked_up_to),
        "slots": [None if m is None else mark_json(m) for m in t.slots],
    }


def _week(w: Week) -> dict:
    return {"start": w.start.isoformat(), "end": w.end.isoformat(), "label": w.label, "glance": w.glance,
            "hours": w.hours, "tasks": [_task(t) for t in w.tasks]}


def _category(c: Category) -> dict:
    return {"key": c.key, "label": c.label, "description": c.description, "builtin": c.builtin}


def board_json(board: Board, reply: Reply | None = None) -> dict:
    events: dict[str, list] = {}
    for e in board.events:
        events.setdefault(e.day.isoformat(), []).append({"t": e.text, "k": e.kind})
    current = board.problems.current
    out = {
        "today": board.today.isoformat(),
        "pages": board.pages,
        "pages_target": board.pages_target,
        "problem": None if current is None else {"number": current.number, "title": current.title},
        # the next problems too, so an offline phone can advance the list itself
        "upcoming": [{"number": p.number, "title": p.title}
                     for p in board.problems.problems[board.problems.position:board.problems.position + UPCOMING]],
        "categories": [_category(c) for c in board.categories],
        "events": events,
        "weeks": [_week(w) for w in board.weeks],
    }
    if reply and reply.notice:
        out["notice"] = reply.notice
    if reply and reply.sync is not None:
        out["sync"] = {"results": [{"id": r.id, "ok": r.ok, "error": r.error} for r in reply.sync.results]}
    if reply and reply.undo:
        out["undo"] = {"task_id": reply.undo.task_id, "slot": reply.undo.slot, **mark_json(reply.undo.mark)}
    return out
