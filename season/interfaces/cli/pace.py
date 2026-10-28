"""Pace command: the thesis deadline against the boxes already on the board.

    python -m season.interfaces.cli.pace              print the line
    python -m season.interfaces.cli.pace --notify     notify too, but only when short
    python -m season.interfaces.cli.pace --quiet      print nothing unless short

Cron uses `--quiet --notify`: on a normal day it writes nothing at all, so the
job is silent; it speaks on the days the menu no longer covers the pages.
"""

import sys

from season.config import load_settings
from season.container import build_app
from season.interfaces.cli.remind import utf8_stdout


def main(argv: list[str]) -> int:
    utf8_stdout()
    app = build_app(load_settings())
    status = app.get_week_status()
    pace = status.pace
    if pace is None:
        if "--quiet" not in argv:
            print("No deadline in the plan.")
        return 0
    if not pace.wake:
        if "--quiet" not in argv:
            print(pace.line())
        return 0
    if "--notify" in argv:
        app.notifier.notify("Thesis pace", pace.line())
    print(pace.line())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
