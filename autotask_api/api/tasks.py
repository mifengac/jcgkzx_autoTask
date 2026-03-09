from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from autotask_api.api.serializers import serialize_task
from autotask_api.database import get_db
from autotask_api.models import AlertTask, MessageTemplate, ScriptDefinition, ScriptVersion, TaskSchedule
from autotask_api.schemas import TaskCreate, TaskRead, TaskScheduleUpsert, TaskUpdate
from autotask_api.services.rule_engine import dump_json_text
from autotask_api.services.scheduler import scheduler_service


router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def task_query():
    return select(AlertTask).options(
        selectinload(AlertTask.schedules),
        selectinload(AlertTask.rules),
    )


def get_task_or_404(db: Session, task_id: int) -> AlertTask:
    task = db.scalar(task_query().where(AlertTask.id == task_id))
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    return task


def validate_foreign_keys(
    db: Session,
    payload: TaskCreate | TaskUpdate,
    current_task: AlertTask | None = None,
) -> None:
    data = payload.model_dump(exclude_unset=True)
    script_id = data.get("script_id", current_task.script_id if current_task else None)
    script = None
    if script_id is not None and not db.get(ScriptDefinition, script_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="script_id not found.")
    if script_id is not None:
        script = db.get(ScriptDefinition, script_id)

    script_version_id = data.get(
        "script_version_id",
        current_task.script_version_id if current_task else None,
    )
    script_version = None
    if script_version_id is not None and not db.get(ScriptVersion, script_version_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="script_version_id not found."
        )
    if script_version_id is not None:
        script_version = db.get(ScriptVersion, script_version_id)
        if script and script_version and script_version.script_id != script.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="script_version_id does not belong to script_id.",
            )

    message_template_id = data.get("message_template_id")
    if message_template_id is not None and not db.get(MessageTemplate, message_template_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="message_template_id not found."
        )


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)) -> TaskRead:
    validate_foreign_keys(db, payload)
    task = AlertTask(
        task_name=payload.task_name,
        script_id=payload.script_id,
        script_version_id=payload.script_version_id,
        message_template_id=payload.message_template_id,
        enabled=payload.enabled,
        dedup_key_expr=payload.dedup_key_expr,
        dedup_window_minutes=payload.dedup_window_minutes,
        runtime_config_json=dump_json_text(payload.runtime_config),
    )
    db.add(task)
    db.flush()

    if payload.schedule:
        schedule = TaskSchedule(task_id=task.id, **payload.schedule.model_dump())
        db.add(schedule)

    db.commit()
    scheduler_service.reload_jobs()
    task = get_task_or_404(db, task.id)
    return serialize_task(task)


@router.get("", response_model=list[TaskRead])
def list_tasks(db: Session = Depends(get_db)) -> list[TaskRead]:
    tasks = db.scalars(task_query().order_by(AlertTask.id.desc())).all()
    return [serialize_task(task) for task in tasks]


@router.get("/{task_id}", response_model=TaskRead)
def get_task(task_id: int, db: Session = Depends(get_db)) -> TaskRead:
    return serialize_task(get_task_or_404(db, task_id))


@router.put("/{task_id}", response_model=TaskRead)
def update_task(task_id: int, payload: TaskUpdate, db: Session = Depends(get_db)) -> TaskRead:
    task = get_task_or_404(db, task_id)
    validate_foreign_keys(db, payload, current_task=task)
    data = payload.model_dump(exclude_unset=True)

    runtime_config = data.pop("runtime_config", None)
    if runtime_config is not None:
        task.runtime_config_json = dump_json_text(runtime_config)

    for key, value in data.items():
        setattr(task, key, value)

    db.add(task)
    db.commit()
    scheduler_service.reload_jobs()
    db.refresh(task)
    return serialize_task(get_task_or_404(db, task_id))


@router.put("/{task_id}/schedule", response_model=TaskRead)
def upsert_schedule(
    task_id: int,
    payload: TaskScheduleUpsert,
    db: Session = Depends(get_db),
) -> TaskRead:
    task = get_task_or_404(db, task_id)
    schedule = task.schedules[0] if task.schedules else None
    if not schedule:
        schedule = TaskSchedule(task_id=task.id, **payload.model_dump())
        db.add(schedule)
    else:
        for key, value in payload.model_dump().items():
            setattr(schedule, key, value)
        db.add(schedule)
    db.commit()
    scheduler_service.reload_jobs()
    return serialize_task(get_task_or_404(db, task_id))


@router.post("/{task_id}/enable", response_model=TaskRead)
def enable_task(task_id: int, db: Session = Depends(get_db)) -> TaskRead:
    task = get_task_or_404(db, task_id)
    task.enabled = True
    db.add(task)
    db.commit()
    scheduler_service.reload_jobs()
    return serialize_task(get_task_or_404(db, task_id))


@router.post("/{task_id}/disable", response_model=TaskRead)
def disable_task(task_id: int, db: Session = Depends(get_db)) -> TaskRead:
    task = get_task_or_404(db, task_id)
    task.enabled = False
    db.add(task)
    db.commit()
    scheduler_service.reload_jobs()
    return serialize_task(get_task_or_404(db, task_id))
