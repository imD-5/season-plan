# Season board

> **This is my vibe-coding test.** It was built by talking to an AI agent, not written by hand line by line.
> It is meant for **personal use only**: it is shaped around my own schedule and is not a product, a library,
> or something I support.

A weekly menu of 1–2 hour work sessions for one season: thesis, LeetCode, job prep, a side project. It is not
a timetable. Each week has a short list of sessions; I pick whatever I feel like and tick a box when one is done.
It runs as a small local server with a SQLite database and opens as its own window on macOS and Windows.

## What it does

- **Weekly menu, no daily tasks.** Each week lists sessions with a rough time per session. Unfinished
  sessions don't carry over.
- **Day strip.** Shows today, fixed events (lab meetings, holidays, deadlines), and what got done on which day.
- **Notes.** Ticking a box opens an optional note for that session. Unchecking or editing a note can be undone.
- **Auto-sorted tasks.** New tasks are sorted into types by [Jev](https://docs.typesafe.ai) (TypeSafe AI).
  If it's unsure or offline, the task goes to *other*. Types can be changed or created from the board.
- **LeetCode queue.** Follows Top Interview 150 and records which problem each session was.
- **Reminders.** Short Monday / Wednesday / Friday / Sunday summaries via a CLI command (I run these from
  a scheduler).

## Running it

Works on **macOS** and **Windows** (Linux runs the server; open the board in a browser). Needs
[uv](https://docs.astral.sh/uv/); `uv sync` installs Python 3.14 if you don't have it.

**macOS** (Terminal)

```sh
uv sync                         # create .venv from uv.lock
cp .env.example .env            # optional: add TYPESAFE_API_KEY for task sorting
cp plan.example.py plan.py      # then make it your own: tasks, events, dates
uv run seed.py                  # load plan.py into season.db
app/macos/install-server.sh     # run the server in the background, also at login (launchd)
app/macos/build.sh              # build ~/Applications/Season.app
```

**Windows** (PowerShell)

```powershell
uv sync
copy .env.example .env
copy plan.example.py plan.py
uv run seed.py
powershell -ExecutionPolicy Bypass -File app\windows\install.ps1   # server at sign-in + "Season" in the Start menu
```

"Season" opens the board in its own Edge window (no tabs or address bar) and starts the server if it isn't
running. No admin rights needed. To undo: the same command with `-Remove`.

Without the installers, `uv run serve.py` starts the server and the board is at http://127.0.0.1:8765/.

**On your iPhone** (through [Tailscale](https://tailscale.com), so only your own devices can reach it)

1. On the Mac: `tailscale serve --bg 8765` and note the `https://…ts.net` address it prints.
2. Put that address in `.env` as `SEASON_ALLOWED_ORIGINS=https://…ts.net` and restart the server.
3. On the iPhone: sign in to the Tailscale app with the same account, open the address in Safari,
   then Share → **Add to Home Screen**.

The board then opens full screen from its own icon. The Mac has to be on; the data stays on the Mac.

The plan (weeks, events, types, the numbered problem queue) is plain data in `plan.py`. **It is yours and
git-ignored** — `plan.example.py` is the generic starting point, and `plan.py` is what the board actually
reads. Edit it any time and re-run `uv run seed.py`; ticks, notes, added tasks and manually chosen types
are kept.

## Development

```sh
uv run python -m unittest discover -s tests -t .   # tests
uvx ruff check season tests                         # lint
```

The code follows a layered (clean architecture) layout: `domain` → `application` → `adapters` /
`interfaces`, wired together in `season/container.py`. A test enforces that inner layers never import outer
ones. `PLAN.md` is my own operations notes and is git-ignored, like `plan.py`.

## Not included

`.env` (API key and personal context), `plan.py` (my own tasks and dates), `season.db` (progress and
notes) and `LOG.md` (weekly log) stay on my machine and are git-ignored.
