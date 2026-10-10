"""Example plan — a starting point, not a working schedule.

Copy this to `plan.py` and make it yours:

    cp plan.example.py plan.py && uv run seed.py

`plan.py` is git-ignored, so your real tasks, dates and notes stay on your machine. Edit `plan.py`
any time and re-run `uv run seed.py`; ticks, notes, added tasks and manually chosen types are kept.

Everything below is placeholder data. Pure data, no behaviour.
"""

from datetime import date, timedelta

from season.application.plan import Plan, PlanCategory, PlanEvent, PlanTask, PlanWeek

TODAY = date.today()
MONDAY = TODAY - timedelta(days=TODAY.weekday())   # the week you are in


def week(n: int) -> date:
    return MONDAY + timedelta(days=7 * n)


# ── types (Jev picks among these; "other" catches anything else) ───────────
# key, label, description. The description is what Jev reads when sorting tasks.
CATEGORIES = (
    PlanCategory("thesis", "thesis", "Long-form writing: drafting, revising, figures, citations"),
    PlanCategory("slides", "slides", "Preparing slides or a talk"),
    PlanCategory("practice", "practice", "Deliberate practice on a skill: coding problems, drilling"),
    PlanCategory("network", "network", "Contacting people: messages, calls, coffee chats, follow-ups"),
    PlanCategory("project", "project", "Personal software project"),
    PlanCategory("admin", "admin", "Paperwork, applications, email, appointments"),
    PlanCategory("other", "other", "Anything that does not clearly fit one of the other types"),
)


# ── fixed events (they show in the day strip) ──────────────────────────────
def ev(day: date, text: str, kind: str = "") -> PlanEvent:
    """kind: "" normal, "me" yours to run, "due" a deadline, "off" a day off, "her" someone else's."""
    return PlanEvent(day, text, kind)


EVENTS = (
    ev(TODAY, "Set your own plan", "me"),
    ev(week(0) + timedelta(days=4), "Weekly review"),          # Friday of this week
    ev(week(1), "Repeating event"),                            # Monday next week
    ev(week(2) + timedelta(days=2), "Deadline", "due"),
    ev(week(3), "Day off", "off"),
)

# A repeating event is just a loop:
# _d = MONDAY
# while _d <= week(12):
#     EVENTS += (ev(_d, "Repeat this", ""),)
#     _d += timedelta(days=7)


# ── the weekly menu ────────────────────────────────────────────────────────
def task(key: str, category: str, text: str, sessions: int, hours_each: float) -> PlanTask:
    """sessions = how many 1-2h sittings the week offers. Rough is fine."""
    return PlanTask(key, category, text, sessions, hours_each)


WEEKS = (
    PlanWeek(week(0), "First week. Pick whatever you feel like.", (
        task("thesis", "thesis", "Draft the section you keep avoiding", 3, 2),
        task("practice", "practice", "Practice problems", 2, 1),
        task("project", "project", "Get the project running end to end", 2, 2),
    )),
    PlanWeek(week(1), "Second week.", (
        task("thesis", "thesis", "Revise what you drafted", 2, 2),
        task("practice", "practice", "Practice problems", 3, 1),
        task("network", "network", "Message two people", 1, 1),
    )),
    PlanWeek(week(2), "Crunch week — deadline Thursday.", (
        task("thesis", "thesis", "Push to the deadline", 5, 2),
        task("slides", "slides", "Slides for the review", 2, 2),
    )),
)


# ── a queue of numbered items, if your practice has a fixed list ───────────
# LeetCode Top Interview 150 here; any (number, title) list works. Leave empty
# for no queue. The board shows the current one and advances when you tick it.
PROBLEMS = (
    (1, "Two sum"),
    (49, "Group anagrams"),
    (217, "Contains duplicate"),
    (242, "Valid anagram"),
    (347, "Top k frequent elements"),
    (271, "Encode and decode strings"),
    (238, "Product of array except self"),
    (36, "Valid sudoku"),
    (128, "Longest consecutive sequence"),
    (125, "Valid palindrome"),
    (15, "3sum"),
    (11, "Container with most water"),
)

PLAN = Plan(categories=CATEGORIES, weeks=WEEKS, events=EVENTS, problems=PROBLEMS)
