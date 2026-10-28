import unittest
from datetime import date

from season.domain.errors import InvalidInput, NotFound
from season.domain.model import OTHER, AssignedBy

from .support import MONDAY, FixedClock, ScriptedClassifier, make_app, task


class SessionTest(unittest.TestCase):
    def setUp(self):
        self.clock = FixedClock(date(2026, 10, 14))
        self.app, self.tmp = make_app(clock=self.clock)

    def tearDown(self):
        self.tmp.cleanup()

    def test_mark_records_today(self):
        t = task(self.app, 0, "thesis")
        self.app.mark_session(t.id, 1)
        self.assertEqual(task(self.app, 0, "thesis").slots[1].done_on, date(2026, 10, 14))

    def test_mark_twice_keeps_first_date(self):
        t = task(self.app, 0, "thesis")
        self.app.mark_session(t.id, 0)
        self.clock.day = date(2026, 10, 15)
        self.app.mark_session(t.id, 0)
        self.assertEqual(task(self.app, 0, "thesis").slots[0].done_on, date(2026, 10, 14))

    def test_leetcode_mark_records_problem_and_advances(self):
        lc = task(self.app, 0, "lc")
        self.app.mark_session(lc.id, 0)
        self.assertEqual(task(self.app, 0, "lc").slots[0].problem, 117)
        self.assertEqual(self.app.get_board().problems.current.number, 114)
        self.app.unmark_session(lc.id, 0)
        self.assertEqual(self.app.get_board().problems.current.number, 117)

    def test_bad_slot_and_missing_task(self):
        with self.assertRaises(InvalidInput):
            self.app.mark_session(task(self.app, 0, "thesis").id, 9)
        with self.assertRaises(NotFound):
            self.app.mark_session(9999, 0)

    def test_skip_problem(self):
        self.app.skip_problem()
        self.assertEqual(self.app.get_board().problems.current.number, 114)


class NoteTest(unittest.TestCase):
    def setUp(self):
        self.app, self.tmp = make_app(clock=FixedClock(date(2026, 10, 14)))
        self.tid = task(self.app, 0, "thesis").id

    def tearDown(self):
        self.tmp.cleanup()

    def note(self):
        return task(self.app, 0, "thesis").slots[0].note

    def test_add_change_clear(self):
        self.app.mark_session(self.tid, 0)
        self.app.set_session_note(self.tid, 0, "  wrote 3 pages of ch.2 ")
        self.assertEqual(self.note(), "wrote 3 pages of ch.2")
        self.app.set_session_note(self.tid, 0, "wrote 4 pages")
        self.assertEqual(self.note(), "wrote 4 pages")
        self.app.set_session_note(self.tid, 0, "   ")
        self.assertIsNone(self.note())

    def test_note_needs_checked_box_and_limit(self):
        with self.assertRaises(InvalidInput):
            self.app.set_session_note(self.tid, 0, "x")
        self.app.mark_session(self.tid, 0)
        with self.assertRaises(InvalidInput):
            self.app.set_session_note(self.tid, 0, "x" * 501)

    def test_uncheck_then_undo_restores_date_and_note(self):
        self.app.mark_session(self.tid, 0)
        self.app.set_session_note(self.tid, 0, "intro draft")
        removed = self.app.unmark_session(self.tid, 0)
        self.assertIsNone(task(self.app, 0, "thesis").slots[0])
        self.app.restore_session(self.tid, 0, removed)
        back = task(self.app, 0, "thesis").slots[0]
        self.assertEqual((back.done_on, back.note), (date(2026, 10, 14), "intro draft"))

    def test_undo_leetcode_moves_queue_forward_again(self):
        lc = task(self.app, 0, "lc").id
        self.app.mark_session(lc, 0)
        removed = self.app.unmark_session(lc, 0)
        self.assertEqual(self.app.get_board().problems.current.number, 117)
        self.app.restore_session(lc, 0, removed)
        self.assertEqual(self.app.get_board().problems.current.number, 114)
        self.assertEqual(task(self.app, 0, "lc").slots[0].problem, 117)

    def test_cannot_restore_over_checked_box(self):
        self.app.mark_session(self.tid, 0)
        removed = self.app.unmark_session(self.tid, 0)
        self.app.mark_session(self.tid, 0)
        with self.assertRaises(InvalidInput):
            self.app.restore_session(self.tid, 0, removed)


class DateTest(unittest.TestCase):
    """Changing the day a checked session was done."""

    def setUp(self):
        self.clock = FixedClock(date(2026, 10, 14))      # Wednesday of the first week
        self.app, self.tmp = make_app(clock=self.clock)
        self.tid = task(self.app, 0, "thesis").id

    def tearDown(self):
        self.tmp.cleanup()

    def mark(self):
        return task(self.app, 0, "thesis").slots[0]

    def test_move_to_another_day_of_the_same_week(self):
        self.app.mark_session(self.tid, 0)
        self.assertEqual(self.app.set_session_date(self.tid, 0, date(2026, 10, 13)), date(2026, 10, 14))
        self.assertEqual(self.mark().done_on, date(2026, 10, 13))

    def test_note_and_problem_stay_when_the_day_moves(self):
        self.app.mark_session(self.tid, 0)
        self.app.set_session_note(self.tid, 0, "fixed fig 3")
        self.app.set_session_date(self.tid, 0, date(2026, 10, 12))
        self.assertEqual((self.mark().done_on, self.mark().note), (date(2026, 10, 12), "fixed fig 3"))

    def test_day_must_stay_in_the_week_and_out_of_the_future(self):
        self.app.mark_session(self.tid, 0)
        with self.assertRaises(InvalidInput):
            self.app.set_session_date(self.tid, 0, date(2026, 10, 11))   # Sunday before
        with self.assertRaises(InvalidInput):
            self.app.set_session_date(self.tid, 0, date(2026, 10, 19))   # next week
        with self.assertRaises(InvalidInput):
            self.app.set_session_date(self.tid, 0, date(2026, 10, 15))   # tomorrow
        self.assertEqual(self.mark().done_on, date(2026, 10, 14))

    def test_needs_a_checked_box(self):
        with self.assertRaises(InvalidInput):
            self.app.set_session_date(self.tid, 0, date(2026, 10, 13))


class AddTaskTest(unittest.TestCase):
    def tearDown(self):
        self.tmp.cleanup()

    def test_confident_prediction_is_used(self):
        self.app, self.tmp = make_app(ScriptedClassifier({"related work": ("thesis", 0.93)}))
        t = self.app.add_task(MONDAY, "Draft related work")
        self.assertEqual((t.category, t.assigned_by, t.confidence), ("thesis", AssignedBy.JEV, 0.93))
        self.assertTrue(t.user_added)

    def test_unsure_prediction_falls_back_to_other(self):
        self.app, self.tmp = make_app(ScriptedClassifier({"related work": ("thesis", 0.3)}))
        t = self.app.add_task(MONDAY, "Draft related work")
        self.assertEqual((t.category, t.assigned_by), (OTHER, AssignedBy.FALLBACK))

    def test_classifier_down_falls_back_to_other(self):
        self.app, self.tmp = make_app(ScriptedClassifier(down=True))
        t = self.app.add_task(MONDAY, "Buy ski wax")
        self.assertEqual((t.category, t.assigned_by, t.confidence), (OTHER, AssignedBy.FALLBACK, None))

    def test_unknown_week(self):
        self.app, self.tmp = make_app()
        with self.assertRaises(NotFound):
            self.app.add_task(date(2030, 1, 7), "x")

    def test_only_added_tasks_can_be_removed(self):
        self.app, self.tmp = make_app()
        with self.assertRaises(InvalidInput):
            self.app.remove_task(task(self.app, 0, "thesis").id)
        t = self.app.add_task(MONDAY, "Buy ski wax")
        self.app.remove_task(t.id)
        self.assertNotIn(t.id, [x.id for x in self.app.get_board().weeks[0].tasks])

    def test_size_from_shorthand_or_arguments(self):
        self.app, self.tmp = make_app()
        t = self.app.add_task(MONDAY, "Read related papers 3x2h")
        self.assertEqual((t.text, t.sessions, t.hours_each), ("Read related papers", 3, 2.0))
        t = self.app.add_task(MONDAY, "Buy ski wax")
        self.assertEqual((t.sessions, t.hours_each), (1, 1.0))           # default: 1 box of 1h
        t = self.app.add_task(MONDAY, "Mock interview 2h", sessions=2)   # argument wins, shorthand fills in
        self.assertEqual((t.text, t.sessions, t.hours_each), ("Mock interview", 2, 2.0))

    def test_bad_size_is_rejected_before_classifying(self):
        classifier = ScriptedClassifier()
        self.app, self.tmp = make_app(classifier)
        with self.assertRaises(InvalidInput):
            self.app.add_task(MONDAY, "Too much 20x1h")
        self.assertEqual(classifier.calls, [])


class ResizeTest(unittest.TestCase):
    def setUp(self):
        self.app, self.tmp = make_app()

    def tearDown(self):
        self.tmp.cleanup()

    def test_resize_added_and_planned(self):
        added = self.app.add_task(MONDAY, "Buy ski wax")
        self.app.resize_task(added.id, 4, 0.5)
        got = next(t for t in self.app.get_board().weeks[0].tasks if t.id == added.id)
        self.assertEqual((got.sessions, got.hours_each), (4, 0.5))
        thesis = task(self.app, 0, "thesis")
        self.app.resize_task(thesis.id, 5, 1.5)
        self.assertEqual((task(self.app, 0, "thesis").sessions, task(self.app, 0, "thesis").hours_each), (5, 1.5))

    def test_cannot_drop_checked_boxes(self):
        thesis = task(self.app, 0, "thesis")          # 3 boxes in the test plan
        self.app.mark_session(thesis.id, 2)
        with self.assertRaises(InvalidInput):
            self.app.resize_task(thesis.id, 2, 2)
        self.assertEqual(task(self.app, 0, "thesis").sessions, 3)

    def test_reseed_keeps_hand_set_size(self):
        from .support import PLAN
        thesis, lc = task(self.app, 0, "thesis"), task(self.app, 0, "lc")
        self.app.resize_task(thesis.id, 6, 1)
        self.app.seed_plan(PLAN)
        self.assertEqual((task(self.app, 0, "thesis").sessions, task(self.app, 0, "thesis").hours_each), (6, 1.0))
        self.assertEqual(task(self.app, 0, "lc").sessions, lc.sessions)   # untouched tasks follow the plan

    def test_missing_task(self):
        with self.assertRaises(NotFound):
            self.app.resize_task(9999, 2, 1)


class CategoryTest(unittest.TestCase):
    def setUp(self):
        self.classifier = ScriptedClassifier({"wax": ("ski", 0.88)})
        self.app, self.tmp = make_app(self.classifier)

    def tearDown(self):
        self.tmp.cleanup()

    def test_new_type_resorts_tasks_stuck_in_other(self):
        stuck = self.app.add_task(MONDAY, "Buy ski wax")
        self.assertEqual(stuck.category, OTHER)
        result = self.app.create_category("Ski", "Ski trips and gear")
        self.assertEqual((result.category.key, result.moved), ("ski", 1))
        moved = next(t for t in self.app.get_board().weeks[0].tasks if t.id == stuck.id)
        self.assertEqual((moved.category, moved.assigned_by), ("ski", AssignedBy.JEV))

    def test_manual_choices_are_never_resorted(self):
        t = self.app.add_task(MONDAY, "Buy ski wax")
        self.app.assign_category(t.id, OTHER)
        self.assertEqual(self.app.create_category("Ski", "Ski trips and gear").moved, 0)

    def test_create_and_assign_in_one_step(self):
        t = self.app.add_task(MONDAY, "Renew residence card")
        self.app.create_category("Admin", "Paperwork and errands", task_id=t.id)
        got = next(x for x in self.app.get_board().weeks[0].tasks if x.id == t.id)
        self.assertEqual((got.category, got.assigned_by), ("admin", AssignedBy.MANUAL))

    def test_duplicate_and_unknown(self):
        with self.assertRaises(InvalidInput):
            self.app.create_category("Thesis", "again")
        with self.assertRaises(NotFound):
            self.app.assign_category(task(self.app, 0, "thesis").id, "nope")

    def test_new_type_is_offered_to_classifier(self):
        self.app.create_category("Ski", "Ski trips and gear")
        self.app.add_task(MONDAY, "wax skis")
        self.assertIn("ski", self.classifier.calls[-1][1])


class SeedTest(unittest.TestCase):
    def setUp(self):
        self.app, self.tmp = make_app()

    def tearDown(self):
        self.tmp.cleanup()

    def test_reseed_keeps_marks_added_tasks_and_manual_types(self):
        from .support import PLAN
        thesis = task(self.app, 0, "thesis")
        self.app.mark_session(thesis.id, 0)
        added = self.app.add_task(MONDAY, "Buy ski wax")
        self.app.assign_category(thesis.id, OTHER)
        self.app.seed_plan(PLAN)
        after = task(self.app, 0, "thesis")
        self.assertEqual((after.id, after.category), (thesis.id, OTHER))
        self.assertIsNotNone(after.slots[0])
        self.assertIn(added.id, [t.id for t in self.app.get_board().weeks[0].tasks])

    def test_week_status(self):
        self.app.mark_session(task(self.app, 0, "thesis").id, 0)
        status = self.app.get_week_status()
        self.assertEqual((status.week.start, status.done_by_category["thesis"]), (MONDAY, 1))

    def test_pages(self):
        self.app.set_pages(40)
        self.assertEqual(self.app.get_board().pages, 40)
        with self.assertRaises(InvalidInput):
            self.app.set_pages(101)


if __name__ == "__main__":
    unittest.main()
