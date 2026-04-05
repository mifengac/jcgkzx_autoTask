from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from autotask_api.api.serializers import (
    serialize_theme_sms_log,
    serialize_theme_source_run,
    serialize_theme_topic_result,
)
from autotask_api.database import get_db
from autotask_api.models import ThemeSmsSendLog, ThemeSourceRun, ThemeTopicResult
from autotask_api.schemas import (
    ThemeSmsSendLogRead,
    ThemeSourceRunDetailRead,
    ThemeSourceRunRead,
    ThemeTopicResultRead,
)


router = APIRouter(tags=["theme-runs"])


@router.get("/api/theme-runs", response_model=list[ThemeSourceRunRead])
def list_theme_runs(
    source_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[ThemeSourceRunRead]:
    stmt = select(ThemeSourceRun).order_by(ThemeSourceRun.id.desc()).limit(limit)
    if source_id is not None:
        stmt = stmt.where(ThemeSourceRun.source_id == source_id)
    runs = db.scalars(stmt).all()
    return [serialize_theme_source_run(run) for run in runs]


@router.get("/api/theme-runs/{run_id}", response_model=ThemeSourceRunDetailRead)
def get_theme_run(run_id: int, db: Session = Depends(get_db)) -> ThemeSourceRunDetailRead:
    stmt = (
        select(ThemeSourceRun)
        .options(
            selectinload(ThemeSourceRun.results),
            selectinload(ThemeSourceRun.sms_logs),
        )
        .where(ThemeSourceRun.id == run_id)
    )
    run = db.scalar(stmt)
    if not run:
        raise HTTPException(status_code=404, detail="Theme run not found.")
    base = serialize_theme_source_run(run)
    return ThemeSourceRunDetailRead(
        **base.model_dump(),
        results=[serialize_theme_topic_result(item) for item in run.results],
        sms_logs=[serialize_theme_sms_log(item) for item in run.sms_logs],
    )


@router.get("/api/theme-runs/{run_id}/results", response_model=list[ThemeTopicResultRead])
def list_theme_run_results(run_id: int, db: Session = Depends(get_db)) -> list[ThemeTopicResultRead]:
    items = db.scalars(
        select(ThemeTopicResult)
        .where(ThemeTopicResult.source_run_id == run_id)
        .order_by(ThemeTopicResult.id.asc())
    ).all()
    return [serialize_theme_topic_result(item) for item in items]


@router.get("/api/theme-runs/{run_id}/sms-logs", response_model=list[ThemeSmsSendLogRead])
def list_theme_run_sms_logs(run_id: int, db: Session = Depends(get_db)) -> list[ThemeSmsSendLogRead]:
    items = db.scalars(
        select(ThemeSmsSendLog)
        .where(ThemeSmsSendLog.source_run_id == run_id)
        .order_by(ThemeSmsSendLog.id.asc())
    ).all()
    return [serialize_theme_sms_log(item) for item in items]
