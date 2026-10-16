"""Sync: apply a queue of changes made on another device (the phone) while it was offline.

The phone keeps its own copy of the board, records every change as an operation with a
unique id, and sends the queue when it can reach the server. The server is the source of
truth: it applies the operations in order through the normal use cases and answers with
the full board, which the phone then adopts.

- Each operation id is applied at most once; a resent op gets its recorded result back.
- A task added on the phone carries the phone's own id (`client_key`). Later operations
  may point at it by that id before the phone knows the server's task number.
- An operation that no longer makes sense (task deleted on the Mac meanwhile, box already
  checked) is recorded as failed with a reason and is not retried.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from season.domain.errors import InvalidInput, NotFound
from season.domain.model import SessionMark, check_client_key

from .ports import UnitOfWorkFactory

TaskRef = int | str      # server task id, or the phone's client key for a task it created


# ── operations ─────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class Mark:
    id: str
    task: TaskRef
    slot: int
    done_on: date


@dataclass(frozen=True, slots=True)
class Unmark:
    id: str
    task: TaskRef
    slot: int


@dataclass(frozen=True, slots=True)
class Restore:
    id: str
    task: TaskRef
    slot: int
    done_on: date
    problem: int | None
    note: str | None


@dataclass(frozen=True, slots=True)
class SetNote:
    id: str
    task: TaskRef
    slot: int
    note: str | None


@dataclass(frozen=True, slots=True)
class Add:
    id: str
    client_key: str
    week: date
    text: str
    sessions: int | None = None
    hours: float | None = None


@dataclass(frozen=True, slots=True)
class Remove:
    id: str
    task: TaskRef


@dataclass(frozen=True, slots=True)
class Resize:
    id: str
    task: TaskRef
    sessions: int
    hours: float


@dataclass(frozen=True, slots=True)
class Assign:
    id: str
    task: TaskRef
    category: str


@dataclass(frozen=True, slots=True)
class NewCategory:
    id: str
    label: str
    description: str
    task: TaskRef | None = None


@dataclass(frozen=True, slots=True)
class SetPages:
    id: str
    pages: int | None


@dataclass(frozen=True, slots=True)
class Skip:
    id: str


Op = Mark | Unmark | Restore | SetNote | Add | Remove | Resize | Assign | NewCategory | SetPages | Skip


@dataclass(frozen=True, slots=True)
class OpResult:
    id: str
    ok: bool
    error: str | None = None
    repeated: bool = False      # already applied by an earlier sync

    def to_json(self) -> str:
        return json.dumps({"ok": self.ok, "error": self.error})


@dataclass(frozen=True, slots=True)
class SyncResult:
    results: tuple[OpResult, ...]

    @property
    def failed(self) -> tuple[OpResult, ...]:
        return tuple(r for r in self.results if not r.ok)


MAX_OPS = 500


class ApplySync:
    def __init__(self, uow: UnitOfWorkFactory, app) -> None:
        # `app` is the set of use cases (season.container.App); each op goes through the same
        # rules as the board's own buttons.
        self._uow, self._app = uow, app

    def __call__(self, ops: Sequence[Op]) -> SyncResult:
        if len(ops) > MAX_OPS:
            raise InvalidInput(f"at most {MAX_OPS} changes per sync")
        results = []
        for op in ops:
            with self._uow() as u:
                previous = u.applied_ops.result(op.id)
            if previous is not None:
                data = json.loads(previous)
                results.append(OpResult(op.id, data["ok"], data["error"], repeated=True))
                continue
            try:
                self._apply(op)
                result = OpResult(op.id, True)
            except (InvalidInput, NotFound) as exc:
                result = OpResult(op.id, False, str(exc))
            with self._uow() as u:
                u.applied_ops.record(op.id, result.to_json())
            results.append(result)
        return SyncResult(tuple(results))

    # ── one op ─────────────────────────────────────────────────────────────
    def _task_id(self, ref: TaskRef) -> int:
        if isinstance(ref, int):
            return ref
        with self._uow() as u:
            task = u.tasks.find_by_key(check_client_key(ref))
        if task is None:
            raise NotFound("that task was never added (its add failed or was removed)")
        return task.id

    def _apply(self, op: Op) -> None:
        a = self._app
        match op:
            case Mark():
                a.mark_session(self._task_id(op.task), op.slot, op.done_on)
            case Unmark():
                a.unmark_session(self._task_id(op.task), op.slot)
            case Restore():
                a.restore_session(self._task_id(op.task), op.slot, SessionMark(op.done_on, op.problem, op.note))
            case SetNote():
                a.set_session_note(self._task_id(op.task), op.slot, op.note)
            case Add():
                a.add_task(op.week, op.text, op.sessions, op.hours, client_key=op.client_key)
            case Remove():
                try:
                    a.remove_task(self._task_id(op.task))
                except NotFound:
                    pass          # already gone: the outcome the phone wanted
            case Resize():
                a.resize_task(self._task_id(op.task), op.sessions, op.hours)
            case Assign():
                a.assign_category(self._task_id(op.task), op.category)
            case NewCategory():
                task_id = None if op.task is None else self._task_id(op.task)
                a.create_category(op.label, op.description, task_id)
            case SetPages():
                a.set_pages(op.pages)
            case Skip():
                a.skip_problem()
