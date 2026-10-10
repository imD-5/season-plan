"""Reminder command: one notification plus a plain-text summary of this week.

    python -m season.interfaces.cli.remind            notify (Mon/Wed/Fri/Sun) and print
    python -m season.interfaces.cli.remind --quiet    print only
"""

import sys

from season.application.use_cases import WeekStatus
from season.config import load_settings
from season.container import build_app


def message(status: WeekStatus) -> str:
    weekday = status.today.weekday()
    if weekday == 0:
        body = "New week on the board. Pick anything."
    elif weekday == 2:
        body = ("No thesis session yet this week. Pick one." if status.done_by_category.get("thesis", 0) == 0
                else "Thesis moving. Pick anything, or stop.")
    elif weekday == 4:
        body = "Friday. Don't add more tonight."
    elif weekday == 6:
        body = "Sunday. Next week's menu is ready. Nothing to report."
    else:
        return ""
    if status.today_events:
        body += " Today: " + ", ".join(e.text for e in status.today_events) + "."
    return body


def utf8_stdout() -> None:
    """Dates and names contain en dashes etc.; legacy Windows code pages can't print them."""
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def summary(status: WeekStatus) -> str:
    lines = [f"Week of {status.week.start} ({status.week.label}). Pages: {status.pages}."]
    for t in status.week.tasks:
        done = sum(1 for s in t.slots if s)
        days = sorted({s.done_on.isoformat() for s in t.slots if s})
        lines.append(f"- [{t.category}] {t.text}: {done}/{t.sessions}" + (f" on {', '.join(days)}" if days else ""))
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    utf8_stdout()
    app = build_app(load_settings())
    status = app.get_week_status()
    body = message(status)
    if body and "--quiet" not in argv:
        app.notifier.notify("Season", body)
    print(body or "No check today.")
    print(summary(status))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
