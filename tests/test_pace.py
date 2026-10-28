import math
import unittest
from datetime import date, timedelta

from season.domain.model import AssignedBy, Board, Event, ProblemQueue, SessionMark, Task, Week
from season.domain.pace import DUE_KIND, THESIS, PaceStatus, deadline_from, last_move, measure, pace_for

TODAY = date(2026, 10, 24)
DUE = date(2027, 1, 20)
PER_TASK = 12          # boxes a single task may hold


def _task(sessions: int, hours: float, checked: int = 0, category: str = THESIS,
          week_start: date = TODAY) -> Task:
    marks = {i: SessionMark(week_start + timedelta(days=i % 5)) for i in range(checked)}
    return Task(id=1, week_start=week_start, key="thesis", text="Thesis", category=category,
                assigned_by=AssignedBy.PLAN, confidence=None, sessions=sessions,
                hours_each=hours, position=0, user_added=False, marks=marks)


def _week(start: date, *tasks: Task) -> Week:
    return Week(start, start + timedelta(days=6), "week", "", tuple(tasks))


def _boxes(start: date, boxes: int, hours: float = 2.0, checked: int = 0) -> Week:
    """One week holding `boxes` boxes, split across tasks no larger than a task may be."""
    tasks, left = [], boxes
    while left > 0:
        n = min(left, PER_TASK)
        tasks.append(_task(sessions=n, hours=hours, checked=min(checked, n), week_start=start))
        left, checked = left - n, max(0, checked - n)
    return _week(start, *tasks)


DUE_EVENT = (Event(DUE, "Thesis due", DUE_KIND),)


def _board(weeks, pages: int | None, events=DUE_EVENT) -> Board:
    return Board(today=TODAY, weeks=tuple(weeks), events=tuple(events), categories=(),
                 problems=ProblemQueue(()), pages=pages)


def _rate_one_per_hour(pages: int = 16) -> Week:
    """A finished week that establishes 1 page per thesis hour."""
    return _boxes(TODAY, pages // 2, hours=2.0, checked=pages // 2)


class DeadlineTest(unittest.TestCase):
    def test_no_due_event_means_no_pace(self):
        self.assertIsNone(deadline_from([Event(TODAY, "Lab")], TODAY))
        self.assertIsNone(pace_for(_board([], 10, events=())))

    def test_upcoming_beats_past(self):
        events = [Event(date(2026, 10, 1), "old", DUE_KIND), Event(DUE, "Thesis due", DUE_KIND)]
        self.assertEqual(deadline_from(events, TODAY), DUE)

    def test_past_deadline_still_shows(self):
        events = [Event(date(2026, 10, 1), "old", DUE_KIND), Event(DUE, "later", DUE_KIND)]
        self.assertEqual(deadline_from(events, date(2027, 2, 1)), DUE)

    def test_other_kinds_are_not_deadlines(self):
        self.assertIsNone(deadline_from([Event(DUE, "Thesis due", "me")], TODAY))


class MeasureTest(unittest.TestCase):
    def test_counts_hours_done_and_hours_left(self):
        last_week = TODAY - timedelta(days=7)
        past = _week(last_week, _task(sessions=10, hours=2, checked=6, week_start=last_week))
        now = _week(TODAY, _task(sessions=4, hours=2, checked=1))
        p = measure(_board([past, now], 20), DUE, TODAY)
        self.assertEqual(p.hours_done, 14.0)               # 7 checked boxes, all weeks
        self.assertEqual(p.hours_left, 6.0)                # the past week's leftover is gone

    def test_no_pages_is_unknown(self):
        p = measure(_board([_week(TODAY, _task(4, 2))], None), DUE, TODAY)
        self.assertIs(PaceStatus.UNKNOWN, p.status)
        self.assertIn("No page count", p.line())
        self.assertIsNone(p.estimate)

    def test_target_reached_is_done(self):
        p = measure(_board([_week(TODAY, _task(4, 2))], 100), DUE, TODAY)
        self.assertIs(PaceStatus.DONE, p.status)
        self.assertEqual(p.pages_left, 0)

    def test_past_deadline_is_overdue(self):
        p = measure(_board([_week(TODAY, _task(4, 2))], 40), TODAY - timedelta(days=3), TODAY)
        self.assertIs(PaceStatus.OVERDUE, p.status)
        self.assertIn("Deadline passed", p.line())

    def test_enough_boxes_is_ok(self):
        # 1 page/hour: 84 pages left needs 84h; 42 boxes of 2h booked
        weeks = [_rate_one_per_hour(), _boxes(TODAY, 42)]
        p = measure(_board(weeks, 16), DUE, TODAY)
        self.assertIs(PaceStatus.OK, p.status)
        self.assertEqual(p.hours_left, 84.0)
        self.assertEqual(p.sessions_short, 0)
        self.assertIn("booked", p.line())

    def test_short_plan_says_how_many_boxes(self):
        # 84 pages left needs 84h; 25 boxes of 2h is 50h -> 34h -> 17 boxes short
        weeks = [_rate_one_per_hour(), _boxes(TODAY, 25)]
        p = measure(_board(weeks, 16), DUE, TODAY)
        self.assertIs(PaceStatus.SHORT, p.status)
        self.assertEqual(p.sessions_short, 17)
        self.assertIn("17 boxes short", p.line())

    def test_one_box_short_is_still_short(self):
        # 41 boxes = 82h against 84h needed: two hours, so one box
        weeks = [_rate_one_per_hour(), _boxes(TODAY, 41)]
        p = measure(_board(weeks, 16), DUE, TODAY)
        self.assertIs(PaceStatus.SHORT, p.status)
        self.assertEqual(p.sessions_short, math.ceil(2 / 2))

    def test_other_categories_do_not_count(self):
        weeks = [_week(TODAY, _task(sessions=10, hours=1, category="leetcode"))]
        p = measure(_board(weeks, 16), DUE, TODAY)
        self.assertEqual(p.hours_left, 0)

    def test_hours_after_the_deadline_do_not_count(self):
        # deadline 20 Jan; a week starting 25 Jan is after it and cannot help
        late = _week(DUE + timedelta(days=5), _task(10, 2, week_start=DUE + timedelta(days=5)))
        p = measure(_board([_week(TODAY, _task(4, 2)), late], 16), DUE, TODAY)
        self.assertEqual(p.hours_left, 8.0)

    def test_weekly_need_follows_the_calendar(self):
        p = measure(_board([_week(TODAY, _task(4, 2))], 16), DUE, TODAY)
        self.assertEqual(p.days_left, 88)
        self.assertAlmostEqual(p.pages_per_week, 84 / (88 / 7), places=6)

    def test_line_matches_the_numbers(self):
        p = measure(_board([_rate_one_per_hour(), _boxes(TODAY, 25)], 16), DUE, TODAY)
        self.assertEqual(p.boxes_per_week, 4)          # 6.7 pp/wk at 1 pp/h in 2h boxes
        self.assertEqual(p.line(), "84 pp left · 4 boxes/wk keeps 20 Jan · 50h booked ≈ 50 pp · "
                                   "17 boxes short")


class StallTest(unittest.TestCase):
    def _board_with(self, history, pages=16, weeks=None) -> Board:
        return Board(today=TODAY, weeks=tuple(weeks or [_week(TODAY, _task(4, 2))]),
                     events=DUE_EVENT, categories=(), problems=ProblemQueue(()),
                     pages=pages, pages_history=tuple(history))

    def test_last_move_is_the_latest_change(self):
        history = [(TODAY - timedelta(days=30), 10), (TODAY - timedelta(days=20), 12),
                   (TODAY - timedelta(days=12), 12), (TODAY - timedelta(days=5), 16)]
        self.assertEqual(last_move(history), TODAY - timedelta(days=5))

    def test_one_record_counts_as_no_movement_yet(self):
        self.assertEqual(last_move([(TODAY - timedelta(days=9), 16)]), TODAY - timedelta(days=9))
        self.assertIsNone(last_move([]))

    def test_still_pages_are_stalled(self):
        history = [(TODAY - timedelta(days=25), 16), (TODAY - timedelta(days=2), 16)]
        p = pace_for(self._board_with(history))
        assert p is not None
        self.assertTrue(p.stalled)
        self.assertTrue(p.wake)
        self.assertTrue(p.line().startswith("pages stuck 25 days"), p.line())

    def test_recent_change_is_not_stalled(self):
        history = [(TODAY - timedelta(days=25), 12), (TODAY - timedelta(days=3), 16)]
        p = pace_for(self._board_with(history))
        assert p is not None
        self.assertFalse(p.stalled)
        self.assertFalse(p.line().startswith("pages stuck"))

    def test_a_finished_thesis_is_never_stalled(self):
        p = pace_for(self._board_with([(TODAY - timedelta(days=40), 100)], pages=100))
        assert p is not None
        self.assertFalse(p.stalled)
        self.assertIs(PaceStatus.DONE, p.status)

    def test_ticking_boxes_without_pages_is_not_a_stall(self):
        # research: pages flat for 25 days, but a thesis box was ticked three days ago
        week = _week(TODAY, _task(4, 2, checked=1, week_start=TODAY - timedelta(days=3)))
        p = pace_for(self._board_with([(TODAY - timedelta(days=25), 16)], weeks=[week]))
        assert p is not None
        self.assertEqual(p.stalled_days, 25)
        self.assertEqual(p.ticked_on, TODAY - timedelta(days=3))
        self.assertFalse(p.stalled)
        self.assertFalse(p.line().startswith("pages stuck"))

    def test_no_page_and_no_box_for_two_weeks_is_a_stall(self):
        week = _week(TODAY, _task(4, 2, checked=1, week_start=TODAY - timedelta(days=20)))
        p = pace_for(self._board_with([(TODAY - timedelta(days=30), 16)], weeks=[week]))
        assert p is not None
        self.assertTrue(p.stalled)


if __name__ == "__main__":
    unittest.main()
