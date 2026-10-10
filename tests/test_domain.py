import unittest
from datetime import date

from season.domain.errors import InvalidInput
from season.domain.model import (
    OTHER,
    AssignedBy,
    Category,
    CategoryAssignment,
    Problem,
    ProblemQueue,
    SessionMark,
    Task,
    check_pages,
    check_size,
    clean_task_text,
    parse_size,
)


def _task(**kw) -> Task:
    base = dict(id=1, week_start=date(2026, 10, 12), key="thesis", text="Thesis", category="thesis",
                assigned_by=AssignedBy.PLAN, confidence=None, sessions=3, hours_each=2.0, position=0,
                user_added=False)
    base.update(kw)
    return Task(**base)


class CategoryTest(unittest.TestCase):
    def test_key_from_label_keeps_unicode(self):
        self.assertEqual(Category.key_from_label("Side Quest!"), "side-quest")
        self.assertEqual(Category.key_from_label("研究室 雑務"), "研究室-雑務")

    def test_create_requires_description(self):
        with self.assertRaises(InvalidInput):
            Category.create("errands", "   ")

    def test_create_rejects_symbols_only(self):
        with self.assertRaises(InvalidInput):
            Category.create("!!!", "something")


class TaskTest(unittest.TestCase):
    def test_slots_and_done(self):
        t = _task(marks={0: SessionMark(date(2026, 10, 12))})
        self.assertEqual([bool(s) for s in t.slots], [True, False, False])
        self.assertFalse(t.is_done)
        self.assertTrue(_task(sessions=1, marks={0: SessionMark(date(2026, 10, 12))}).is_done)

    def test_require_slot(self):
        with self.assertRaises(InvalidInput):
            _task().require_slot(3)

    def test_problem_list_only_for_planned_lc(self):
        self.assertTrue(_task(key="lc").tracks_problem_list)
        self.assertFalse(_task(key="lc", user_added=True).tracks_problem_list)

    def test_text_is_cleaned_and_limited(self):
        self.assertEqual(clean_task_text("  draft   intro "), "draft intro")
        with self.assertRaises(InvalidInput):
            clean_task_text("x" * 161)

    def test_with_assignment(self):
        t = _task().with_assignment(CategoryAssignment(OTHER, AssignedBy.FALLBACK, 0.2))
        self.assertEqual((t.category, t.assigned_by, t.confidence), (OTHER, AssignedBy.FALLBACK, 0.2))


class ProblemQueueTest(unittest.TestCase):
    def setUp(self):
        self.q = ProblemQueue((Problem(117, "a"), Problem(114, "b")))

    def test_advance_to_end(self):
        q = self.q.advanced().advanced().advanced()
        self.assertEqual(q.position, 2)
        self.assertIsNone(q.current)

    def test_rewind_only_for_last_completed(self):
        q = self.q.advanced()
        self.assertEqual(q.rewound_for(117).position, 0)
        self.assertEqual(q.rewound_for(999).position, 1)


class SizeTest(unittest.TestCase):
    def test_parse_shorthand(self):
        cases = {
            "Read papers 3x2h": ("Read papers", 3, 2.0),
            "Read papers 3 × 1.5h": ("Read papers", 3, 1.5),
            "Read papers 2X1H": ("Read papers", 2, 1.0),
            "Draft intro 2h": ("Draft intro", None, 2.0),
            "Exercises 4x": ("Exercises", 4, None),
            "Call Kenji 30m": ("Call Kenji", None, 0.5),
            "Call Kenji 20min": ("Call Kenji", None, 0.5),
            "Ch.2 section 3": ("Ch.2 section 3", None, None),     # a bare number is not a size
            "Review 2026 plan": ("Review 2026 plan", None, None),
            "2h": ("2h", None, None),                             # nothing left: keep as text
        }
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_size(text), want)

    def test_check_size_bounds(self):
        self.assertEqual(check_size(3, 1.5), (3, 1.5))
        self.assertEqual(check_size(1, 0), (1, 0.0))
        for bad in ((0, 1), (13, 1), (2, 8.5), (2, 1.25), (2, -1), (True, 1), (2.0, 1)):
            with self.subTest(size=bad), self.assertRaises(InvalidInput):
                check_size(*bad)

    def test_resize_keeps_checked_boxes(self):
        t = _task(sessions=3, marks={1: SessionMark(date(2026, 10, 12))})
        self.assertEqual(t.checked_up_to, 2)
        self.assertEqual(t.resized(2, 1.5).sessions, 2)
        with self.assertRaises(InvalidInput):
            t.resized(1, 2)


class PagesTest(unittest.TestCase):
    def test_bounds(self):
        self.assertIsNone(check_pages(None))
        self.assertEqual(check_pages(42), 42)
        for bad in (-1, 101, True, 1.5):
            with self.assertRaises(InvalidInput):
                check_pages(bad)


if __name__ == "__main__":
    unittest.main()
