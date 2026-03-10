from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from autotask_api.database import get_db
from autotask_api.models import SmsSendLog, TaskRun, TaskRunResult
from autotask_api.schemas import (
    SmsSendLogRead,
    TaskRunDetailRead,
    TaskRunRead,
    TaskRunRequest,
    TaskRunResultRead,
)
from autotask_api.services.rule_engine import parse_json_text
from autotask_api.services.task_fields import normalize_non_null_text_output
from autotask_api.services.task_executor import execute_task_run


router = APIRouter(tags=["task-runs"])


def serialize_task_run(run: TaskRun) -> TaskRunRead:
    return TaskRunRead(
        id=run.id,
        task_id=run.task_id,
        run_no=run.run_no,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        result_count=run.result_count,
        hit_count=run.hit_count,
        send_count=run.send_count,
        error_message=normalize_non_null_text_output(run.error_message),
        log_path=normalize_non_null_text_output(run.log_path),
        created_at=run.created_at,
    )


def serialize_task_run_result(item: TaskRunResult) -> TaskRunResultRead:
    return TaskRunResultRead(
        id=item.id,
        task_run_id=item.task_run_id,
        event_key=item.event_key,
        raw_result=parse_json_text(item.raw_result_json, {}),
        rendered_message=normalize_non_null_text_output(item.rendered_message),
        matched_rule_ids=parse_json_text(item.matched_rule_ids_json, []),
        receiver_mobiles=parse_json_text(item.receiver_mobiles_json, []),
        send_status=item.send_status,
        created_at=item.created_at,
    )


def serialize_sms_log(item: SmsSendLog) -> SmsSendLogRead:
    return SmsSendLogRead(
        id=item.id,
        task_run_id=item.task_run_id,
        task_result_id=item.task_result_id,
        mobile=item.mobile,
        content=item.content,
        provider=item.provider,
        provider_msg_id=normalize_non_null_text_output(item.provider_msg_id),
        status=item.status,
        error_message=normalize_non_null_text_output(item.error_message),
        created_at=item.created_at,
    )


@router.post("/api/tasks/{task_id}/run", response_model=TaskRunRead, status_code=status.HTTP_202_ACCEPTED)
def run_task(
    task_id: int,
    payload: TaskRunRequest,
    db: Session = Depends(get_db),
) -> TaskRunRead:
    run = execute_task_run(db, task_id, payload)
    return serialize_task_run(run)


@router.get("/api/task-runs", response_model=list[TaskRunRead])
def list_task_runs(
    task_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[TaskRunRead]:
    stmt = select(TaskRun).order_by(TaskRun.id.desc()).limit(limit)
    if task_id is not None:
        stmt = stmt.where(TaskRun.task_id == task_id)
    runs = db.scalars(stmt).all()
    return [serialize_task_run(run) for run in runs]


@router.get("/api/task-runs/{run_id}", response_model=TaskRunDetailRead)
def get_task_run(run_id: int, db: Session = Depends(get_db)) -> TaskRunDetailRead:
    stmt = (
        select(TaskRun)
        .options(
            selectinload(TaskRun.results),
            selectinload(TaskRun.sms_logs),
        )
        .where(TaskRun.id == run_id)
    )
    run = db.scalar(stmt)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task run not found.")
    base = serialize_task_run(run)
    return TaskRunDetailRead(
        **base.model_dump(),
        results=[serialize_task_run_result(item) for item in run.results],
        sms_logs=[serialize_sms_log(item) for item in run.sms_logs],
    )


@router.get("/api/task-runs/{run_id}/results", response_model=list[TaskRunResultRead])
def list_task_run_results(run_id: int, db: Session = Depends(get_db)) -> list[TaskRunResultRead]:
    items = db.scalars(
        select(TaskRunResult).where(TaskRunResult.task_run_id == run_id).order_by(TaskRunResult.id.asc())
    ).all()
    return [serialize_task_run_result(item) for item in items]


@router.get("/api/task-runs/{run_id}/sms-logs", response_model=list[SmsSendLogRead])
def list_task_run_sms_logs(run_id: int, db: Session = Depends(get_db)) -> list[SmsSendLogRead]:
    items = db.scalars(
        select(SmsSendLog).where(SmsSendLog.task_run_id == run_id).order_by(SmsSendLog.id.asc())
    ).all()
    return [serialize_sms_log(item) for item in items]
