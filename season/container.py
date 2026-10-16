"""Composition root: the only place that knows every layer and wires them."""

from dataclasses import dataclass, replace

from season.adapters.jev_classifier import JevClassifier, UnavailableClassifier
from season.adapters.sqlite_store import SqliteDatabase
from season.adapters.system import SystemClock, default_notifier
from season.application import use_cases as uc
from season.application.ports import Classifier, Clock, Notifier
from season.application.sync import ApplySync
from season.config import Settings


@dataclass(frozen=True, slots=True)
class App:
    settings: Settings
    notifier: Notifier
    get_board: uc.GetBoard
    get_week_status: uc.GetWeekStatus
    mark_session: uc.MarkSession
    unmark_session: uc.UnmarkSession
    restore_session: uc.RestoreSession
    set_session_note: uc.SetSessionNote
    skip_problem: uc.SkipProblem
    add_task: uc.AddTask
    resize_task: uc.ResizeTask
    remove_task: uc.RemoveTask
    assign_category: uc.AssignCategory
    create_category: uc.CreateCategory
    set_pages: uc.SetPages
    seed_plan: uc.SeedPlan
    apply_sync: ApplySync | None = None


def build_app(settings: Settings, *, classifier: Classifier | None = None,
              clock: Clock | None = None, notifier: Notifier | None = None) -> App:
    db = SqliteDatabase(settings.db_path)
    db.migrate()
    uow = db.unit_of_work
    clock = clock or SystemClock()
    if classifier is None:
        classifier = (JevClassifier(settings.typesafe_api_key, settings.typesafe_model, context=settings.context)
                      if settings.typesafe_api_key else UnavailableClassifier())
    policy = uc.ClassificationPolicy(settings.min_probability)
    get_board = uc.GetBoard(uow, clock)
    app = App(
        settings=settings,
        notifier=notifier or default_notifier(),
        get_board=get_board,
        get_week_status=uc.GetWeekStatus(get_board),
        mark_session=uc.MarkSession(uow, clock),
        unmark_session=uc.UnmarkSession(uow),
        restore_session=uc.RestoreSession(uow),
        set_session_note=uc.SetSessionNote(uow),
        skip_problem=uc.SkipProblem(uow),
        add_task=uc.AddTask(uow, classifier, policy),
        resize_task=uc.ResizeTask(uow),
        remove_task=uc.RemoveTask(uow),
        assign_category=uc.AssignCategory(uow),
        create_category=uc.CreateCategory(uow, classifier, policy),
        set_pages=uc.SetPages(uow),
        seed_plan=uc.SeedPlan(uow),
    )
    return replace(app, apply_sync=ApplySync(uow, app))
