"""JSON -> sync operations. Validation of shapes only; the rules live in the use cases."""

from datetime import date

from season.application import sync as s
from season.domain.errors import InvalidInput


def _get(op: dict, key: str, kind, *, optional: bool = False):
    if key not in op or op[key] is None:
        if optional:
            return None
        raise InvalidInput(f"{key} is required")
    value = op[key]
    if kind is int and (isinstance(value, bool) or not isinstance(value, int)):
        raise InvalidInput(f"{key} must be a whole number")
    if kind is float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InvalidInput(f"{key} must be a number")
        return float(value)
    if kind is str and not isinstance(value, str):
        raise InvalidInput(f"{key} must be text")
    if kind is date:
        try:
            return date.fromisoformat(_get(op, key, str))
        except ValueError as exc:
            raise InvalidInput(f"{key} must be a date like 2026-10-12") from exc
    return value


def _task(op: dict, key: str = "task", optional: bool = False) -> s.TaskRef | None:
    value = op.get(key)
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise InvalidInput(f"{key} must be a task id or a client task id")
    return value


def parse_op(op: object) -> s.Op:
    if not isinstance(op, dict):
        raise InvalidInput("each change must be an object")
    op_id = _get(op, "id", str)
    if not 8 <= len(op_id) <= 64:
        raise InvalidInput("change id must be 8-64 characters")
    kind = _get(op, "kind", str)
    match kind:
        case "mark":
            return s.Mark(op_id, _task(op), _get(op, "slot", int), _get(op, "d", date))
        case "unmark":
            return s.Unmark(op_id, _task(op), _get(op, "slot", int))
        case "restore":
            return s.Restore(op_id, _task(op), _get(op, "slot", int), _get(op, "d", date),
                             _get(op, "problem", int, optional=True), _get(op, "note", str, optional=True))
        case "note":
            return s.SetNote(op_id, _task(op), _get(op, "slot", int), _get(op, "note", str, optional=True))
        case "date":
            return s.SetDate(op_id, _task(op), _get(op, "slot", int), _get(op, "d", date))
        case "add":
            return s.Add(op_id, _get(op, "client_key", str), _get(op, "week", date), _get(op, "text", str),
                         _get(op, "sessions", int, optional=True), _get(op, "hours", float, optional=True))
        case "remove":
            return s.Remove(op_id, _task(op))
        case "resize":
            return s.Resize(op_id, _task(op), _get(op, "sessions", int), _get(op, "hours", float))
        case "category":
            return s.Assign(op_id, _task(op), _get(op, "category", str))
        case "new_category":
            return s.NewCategory(op_id, _get(op, "label", str), _get(op, "description", str),
                                 _task(op, optional=True))
        case "pages":
            return s.SetPages(op_id, _get(op, "pages", int, optional=True))
        case "skip":
            return s.Skip(op_id)
    raise InvalidInput(f"unknown change kind {kind!r}")


def parse_ops(body: dict) -> list[s.Op]:
    ops = body.get("ops")
    if not isinstance(ops, list):
        raise InvalidInput("ops must be a list")
    return [parse_op(op) for op in ops]
