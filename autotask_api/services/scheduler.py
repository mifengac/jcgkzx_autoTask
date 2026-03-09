from __future__ import annotations

from collections.abc import Iterable
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from autotask_api.database import SessionLocal
from autotask_api.models import AlertTask
from autotask_api.schemas import TaskRunRequest
from autotask_api.services.task_executor import execute_task_run


LOGGER = logging.getLogger("autotask.scheduler")


class TaskSchedulerService:
    def __init__(self) -> None:
        self.scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
        self.started = False

    def start(self) -> None:
        if self.started:
            return
        self.scheduler.start()
        self.started = True
        self.reload_jobs()
        LOGGER.info("Task scheduler started.")

    def shutdown(self) -> None:
        if not self.started:
            return
        self.scheduler.shutdown(wait=False)
        self.started = False
        LOGGER.info("Task scheduler stopped.")

    def reload_jobs(self) -> None:
        if not self.started:
            return
        self.scheduler.remove_all_jobs()
        with SessionLocal() as db:
            for task in self._load_enabled_tasks(db):
                self._register_task(task)

    def _load_enabled_tasks(self, db: Session) -> Iterable[AlertTask]:
        stmt = (
            select(AlertTask)
            .options(selectinload(AlertTask.schedules))
            .where(AlertTask.enabled.is_(True))
        )
        return db.scalars(stmt).all()

    def _register_task(self, task: AlertTask) -> None:
        active_schedule = next((item for item in task.schedules if item.enabled), None)
        if not active_schedule:
            return

        seconds = active_schedule.interval_value * (
            60 if active_schedule.interval_unit == "minute" else 3600
        )
        trigger = IntervalTrigger(
            seconds=seconds,
            timezone=active_schedule.timezone or "Asia/Shanghai",
            start_date=active_schedule.start_at,
            end_date=active_schedule.end_at,
        )
        self.scheduler.add_job(
            self._run_task_job,
            trigger=trigger,
            args=[task.id],
            id=f"task_{task.id}",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        LOGGER.info(
            "Registered task %s with interval %s %s",
            task.id,
            active_schedule.interval_value,
            active_schedule.interval_unit,
        )

    @staticmethod
    def _run_task_job(task_id: int) -> None:
        with SessionLocal() as db:
            try:
                execute_task_run(
                    db,
                    task_id=task_id,
                    payload=TaskRunRequest(dry_run=False, context_override={}),
                )
            except Exception:
                LOGGER.exception("Scheduled task %s failed.", task_id)


scheduler_service = TaskSchedulerService()
