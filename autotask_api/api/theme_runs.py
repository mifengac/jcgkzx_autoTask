from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from autotask_api.api.serializers import (
    serialize_theme_sms_log_detail,
    serialize_theme_sms_log_summary,
    serialize_theme_sms_log,
    serialize_theme_source_run,
    serialize_theme_topic_result_detail,
    serialize_theme_topic_result_summary,
    serialize_theme_topic_result,
)
from autotask_api.database import get_db
from autotask_api.models import ThemeSmsSendLog, ThemeSourceRun, ThemeTopicResult
from autotask_api.schemas import (
    ThemeSmsSendLogDetailRead,
    ThemeSmsSendLogPageRead,
    ThemeSmsSendLogSummaryRead,
    ThemeSmsSendLogRead,
    ThemeSourceRunDetailRead,
    ThemeSourceRunRead,
    ThemeTopicResultDetailRead,
    ThemeTopicResultPageRead,
    ThemeTopicResultRead,
)


router = APIRouter(tags=["theme-runs"])


@router.get("/api/theme-runs", response_model=list[ThemeSourceRunRead])
def list_theme_runs(
    source_id: int | None = Query(default=None),
    topic_id: int | None = Query(default=None),
    status_text: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[ThemeSourceRunRead]:
    stmt = select(ThemeSourceRun).order_by(ThemeSourceRun.id.desc())
    if source_id is not None:
        stmt = stmt.where(ThemeSourceRun.source_id == source_id)
    if status_text:
        stmt = stmt.where(ThemeSourceRun.status == status_text)
    if topic_id is not None:
        stmt = (
            stmt.join(ThemeSourceRun.results)
            .where(ThemeTopicResult.topic_id == topic_id)
            .distinct()
        )
    stmt = stmt.offset(offset).limit(limit)
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


@router.get("/api/theme-results", response_model=ThemeTopicResultPageRead)
def list_theme_results(
    source_id: int | None = Query(default=None),
    topic_id: int | None = Query(default=None),
    run_id: int | None = Query(default=None),
    send_status: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ThemeTopicResultPageRead:
    stmt = (
        select(ThemeTopicResult)
        .options(
            joinedload(ThemeTopicResult.topic),
            joinedload(ThemeTopicResult.source_run).joinedload(ThemeSourceRun.source),
        )
        .join(ThemeTopicResult.topic)
        .join(ThemeTopicResult.source_run)
        .order_by(ThemeTopicResult.id.desc())
    )
    if source_id is not None:
        stmt = stmt.where(ThemeSourceRun.source_id == source_id)
    if topic_id is not None:
        stmt = stmt.where(ThemeTopicResult.topic_id == topic_id)
    if run_id is not None:
        stmt = stmt.where(ThemeTopicResult.source_run_id == run_id)
    if send_status:
        stmt = stmt.where(ThemeTopicResult.send_status == send_status)
    if start_time is not None:
        stmt = stmt.where(ThemeTopicResult.created_at >= start_time)
    if end_time is not None:
        stmt = stmt.where(ThemeTopicResult.created_at <= end_time)
    if keyword:
        token = f"%{keyword.strip()}%"
        stmt = stmt.where(
            or_(
                ThemeTopicResult.case_no.ilike(token),
                ThemeTopicResult.rendered_message.ilike(token),
                ThemeTopicResult.raw_result_json.ilike(token),
            )
        )
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    items = db.scalars(stmt.offset(offset).limit(limit)).unique().all()
    return ThemeTopicResultPageRead(
        items=[serialize_theme_topic_result_summary(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/api/theme-results/{result_id}", response_model=ThemeTopicResultDetailRead)
def get_theme_result(result_id: int, db: Session = Depends(get_db)) -> ThemeTopicResultDetailRead:
    stmt = (
        select(ThemeTopicResult)
        .options(
            joinedload(ThemeTopicResult.topic),
            joinedload(ThemeTopicResult.source_run).joinedload(ThemeSourceRun.source),
        )
        .where(ThemeTopicResult.id == result_id)
    )
    item = db.scalar(stmt)
    if not item:
        raise HTTPException(status_code=404, detail="Theme result not found.")
    return serialize_theme_topic_result_detail(item)


@router.get("/api/theme-sms-logs", response_model=ThemeSmsSendLogPageRead)
def list_theme_sms_logs(
    source_id: int | None = Query(default=None),
    topic_id: int | None = Query(default=None),
    run_id: int | None = Query(default=None),
    status_text: str | None = Query(default=None, alias="status"),
    mobile: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ThemeSmsSendLogPageRead:
    stmt = (
        select(ThemeSmsSendLog)
        .options(
            joinedload(ThemeSmsSendLog.topic),
            joinedload(ThemeSmsSendLog.source_run).joinedload(ThemeSourceRun.source),
            joinedload(ThemeSmsSendLog.topic_result),
        )
        .join(ThemeSmsSendLog.topic)
        .join(ThemeSmsSendLog.source_run)
        .order_by(ThemeSmsSendLog.id.desc())
    )
    if source_id is not None:
        stmt = stmt.where(ThemeSourceRun.source_id == source_id)
    if topic_id is not None:
        stmt = stmt.where(ThemeSmsSendLog.topic_id == topic_id)
    if run_id is not None:
        stmt = stmt.where(ThemeSmsSendLog.source_run_id == run_id)
    if status_text:
        stmt = stmt.where(ThemeSmsSendLog.status == status_text)
    if mobile:
        stmt = stmt.where(ThemeSmsSendLog.mobile.ilike(f"%{mobile.strip()}%"))
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    items = db.scalars(stmt.offset(offset).limit(limit)).unique().all()
    return ThemeSmsSendLogPageRead(
        items=[serialize_theme_sms_log_summary(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/api/theme-sms-logs/{log_id}", response_model=ThemeSmsSendLogDetailRead)
def get_theme_sms_log(log_id: int, db: Session = Depends(get_db)) -> ThemeSmsSendLogDetailRead:
    stmt = (
        select(ThemeSmsSendLog)
        .options(
            joinedload(ThemeSmsSendLog.topic),
            joinedload(ThemeSmsSendLog.source_run).joinedload(ThemeSourceRun.source),
            joinedload(ThemeSmsSendLog.topic_result),
        )
        .where(ThemeSmsSendLog.id == log_id)
    )
    item = db.scalar(stmt)
    if not item:
        raise HTTPException(status_code=404, detail="Theme SMS log not found.")
    return serialize_theme_sms_log_detail(item)
