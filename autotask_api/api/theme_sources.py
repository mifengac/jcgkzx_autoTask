from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from autotask_api.api.serializers import (
    serialize_theme_receiver_rule,
    serialize_theme_source,
    serialize_theme_source_detail,
    serialize_theme_source_run,
    serialize_theme_topic,
)
from autotask_api.database import get_db
from autotask_api.models import MessageTemplate, ThemeReceiverRule, ThemeSource, ThemeTopic
from autotask_api.schemas import (
    ThemeReceiverRuleCreate,
    ThemeReceiverRuleRead,
    ThemeReceiverRuleUpdate,
    ThemeSourceCreate,
    ThemeSourceDetailRead,
    ThemeSourceRead,
    ThemeSourceRunRead,
    ThemeSourceRunRequest,
    ThemeSourceUpdate,
    ThemeTopicCreate,
    ThemeTopicRead,
    ThemeTopicUpdate,
)
from autotask_api.services.rule_engine import dump_json_text
from autotask_api.services.scheduler import scheduler_service
from autotask_api.services.theme_executor import execute_theme_source_run


router = APIRouter(tags=["theme-sources"])


def theme_source_query():
    return select(ThemeSource).options(
        selectinload(ThemeSource.topics).selectinload(ThemeTopic.receiver_rules),
    )


def get_theme_source_or_404(db: Session, source_id: int) -> ThemeSource:
    source = db.scalar(theme_source_query().where(ThemeSource.id == source_id))
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Theme source not found.")
    return source


def get_theme_topic_or_404(db: Session, topic_id: int) -> ThemeTopic:
    stmt = (
        select(ThemeTopic)
        .options(selectinload(ThemeTopic.receiver_rules))
        .where(ThemeTopic.id == topic_id)
    )
    topic = db.scalar(stmt)
    if not topic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Theme topic not found.")
    return topic


def get_theme_receiver_rule_or_404(db: Session, rule_id: int) -> ThemeReceiverRule:
    rule = db.get(ThemeReceiverRule, rule_id)
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Theme receiver rule not found.",
        )
    return rule


def validate_theme_template(db: Session, message_template_id: int | None) -> None:
    if message_template_id is None:
        return
    if not db.get(MessageTemplate, message_template_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="message_template_id not found.",
        )


def validate_theme_topic_settings(dedup_mode: str, dedup_window_minutes: int | None) -> None:
    if dedup_mode == "window" and not dedup_window_minutes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="dedup_window_minutes is required when dedup_mode=window.",
        )


def apply_theme_source_schedule(source: ThemeSource, payload: ThemeSourceCreate | ThemeSourceUpdate) -> None:
    schedule = payload.schedule
    if schedule is None:
        return
    source.interval_value = schedule.interval_value
    source.interval_unit = schedule.interval_unit
    source.timezone = schedule.timezone
    source.start_at = schedule.start_at
    source.end_at = schedule.end_at


@router.post("/api/theme-sources", response_model=ThemeSourceRead, status_code=status.HTTP_201_CREATED)
def create_theme_source(payload: ThemeSourceCreate, db: Session = Depends(get_db)) -> ThemeSourceRead:
    exists = db.scalar(select(ThemeSource).where(ThemeSource.source_code == payload.source_code))
    if exists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="source_code already exists.",
        )

    source = ThemeSource(
        source_name=payload.source_name,
        source_code=payload.source_code,
        source_type=payload.source_type,
        enabled=payload.enabled,
        source_config_json=dump_json_text(payload.source_config),
    )
    apply_theme_source_schedule(source, payload)
    db.add(source)
    db.commit()
    scheduler_service.reload_jobs()
    return serialize_theme_source(get_theme_source_or_404(db, source.id))


@router.get("/api/theme-sources", response_model=list[ThemeSourceRead])
def list_theme_sources(db: Session = Depends(get_db)) -> list[ThemeSourceRead]:
    sources = db.scalars(theme_source_query().order_by(ThemeSource.id.desc())).all()
    return [serialize_theme_source(source) for source in sources]


@router.get("/api/theme-sources/{source_id}", response_model=ThemeSourceDetailRead)
def get_theme_source(source_id: int, db: Session = Depends(get_db)) -> ThemeSourceDetailRead:
    return serialize_theme_source_detail(get_theme_source_or_404(db, source_id))


@router.put("/api/theme-sources/{source_id}", response_model=ThemeSourceRead)
def update_theme_source(
    source_id: int,
    payload: ThemeSourceUpdate,
    db: Session = Depends(get_db),
) -> ThemeSourceRead:
    source = get_theme_source_or_404(db, source_id)
    data = payload.model_dump(exclude_unset=True)

    if "source_code" in data:
        exists = db.scalar(
            select(ThemeSource).where(
                ThemeSource.source_code == data["source_code"],
                ThemeSource.id != source_id,
            )
        )
        if exists:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="source_code already exists.",
            )

    source_config = data.pop("source_config", None)
    if source_config is not None:
        source.source_config_json = dump_json_text(source_config)

    data.pop("schedule", None)
    for key, value in data.items():
        setattr(source, key, value)

    apply_theme_source_schedule(source, payload)
    db.add(source)
    db.commit()
    scheduler_service.reload_jobs()
    return serialize_theme_source(get_theme_source_or_404(db, source_id))


@router.post("/api/theme-sources/{source_id}/topics", response_model=ThemeTopicRead, status_code=status.HTTP_201_CREATED)
def create_theme_topic(
    source_id: int,
    payload: ThemeTopicCreate,
    db: Session = Depends(get_db),
) -> ThemeTopicRead:
    source = get_theme_source_or_404(db, source_id)
    validate_theme_template(db, payload.message_template_id)
    validate_theme_topic_settings(payload.dedup_mode, payload.dedup_window_minutes)

    exists = db.scalar(select(ThemeTopic).where(ThemeTopic.theme_code == payload.theme_code))
    if exists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="theme_code already exists.",
        )

    topic = ThemeTopic(
        source_id=source.id,
        theme_name=payload.theme_name,
        theme_code=payload.theme_code,
        message_template_id=payload.message_template_id,
        enabled=payload.enabled,
        priority=payload.priority,
        filter_expr_json=dump_json_text(payload.filter_expr),
        dedup_mode=payload.dedup_mode,
        dedup_window_minutes=payload.dedup_window_minutes,
        dedup_key_template=payload.dedup_key_template,
    )
    db.add(topic)
    db.commit()
    return serialize_theme_topic(get_theme_topic_or_404(db, topic.id))


@router.put("/api/theme-topics/{topic_id}", response_model=ThemeTopicRead)
def update_theme_topic(
    topic_id: int,
    payload: ThemeTopicUpdate,
    db: Session = Depends(get_db),
) -> ThemeTopicRead:
    topic = get_theme_topic_or_404(db, topic_id)
    data = payload.model_dump(exclude_unset=True)

    if "theme_code" in data:
        exists = db.scalar(
            select(ThemeTopic).where(
                ThemeTopic.theme_code == data["theme_code"],
                ThemeTopic.id != topic_id,
            )
        )
        if exists:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="theme_code already exists.",
            )

    if "message_template_id" in data:
        validate_theme_template(db, data["message_template_id"])
    validate_theme_topic_settings(
        data.get("dedup_mode", topic.dedup_mode),
        data.get("dedup_window_minutes", topic.dedup_window_minutes),
    )

    filter_expr = data.pop("filter_expr", None)
    if filter_expr is not None:
        topic.filter_expr_json = dump_json_text(filter_expr)

    for key, value in data.items():
        setattr(topic, key, value)

    db.add(topic)
    db.commit()
    return serialize_theme_topic(get_theme_topic_or_404(db, topic_id))


@router.post(
    "/api/theme-topics/{topic_id}/receiver-rules",
    response_model=ThemeReceiverRuleRead,
    status_code=status.HTTP_201_CREATED,
)
def create_theme_receiver_rule(
    topic_id: int,
    payload: ThemeReceiverRuleCreate,
    db: Session = Depends(get_db),
) -> ThemeReceiverRuleRead:
    topic = get_theme_topic_or_404(db, topic_id)
    rule = ThemeReceiverRule(
        topic_id=topic.id,
        rule_name=payload.rule_name,
        rule_type=payload.rule_type,
        priority=payload.priority,
        enabled=payload.enabled,
        source_field=payload.source_field,
        target_table=payload.target_table,
        target_match_field=payload.target_match_field,
        target_mobile_field=payload.target_mobile_field,
        include_self=payload.include_self,
        include_county=payload.include_county,
        include_city=payload.include_city,
        filter_json=dump_json_text(payload.filter_json),
        fixed_receivers_json=dump_json_text(payload.fixed_receivers),
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return serialize_theme_receiver_rule(rule)


@router.put("/api/theme-receiver-rules/{rule_id}", response_model=ThemeReceiverRuleRead)
def update_theme_receiver_rule(
    rule_id: int,
    payload: ThemeReceiverRuleUpdate,
    db: Session = Depends(get_db),
) -> ThemeReceiverRuleRead:
    rule = get_theme_receiver_rule_or_404(db, rule_id)
    data = payload.model_dump(exclude_unset=True)
    if "filter_json" in data:
        rule.filter_json = dump_json_text(data.pop("filter_json"))
    if "fixed_receivers" in data:
        rule.fixed_receivers_json = dump_json_text(data.pop("fixed_receivers"))
    for key, value in data.items():
        setattr(rule, key, value)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return serialize_theme_receiver_rule(rule)


@router.delete("/api/theme-receiver-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_theme_receiver_rule(rule_id: int, db: Session = Depends(get_db)) -> None:
    rule = get_theme_receiver_rule_or_404(db, rule_id)
    db.delete(rule)
    db.commit()


@router.post(
    "/api/theme-sources/{source_id}/run",
    response_model=ThemeSourceRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def run_theme_source(
    source_id: int,
    payload: ThemeSourceRunRequest,
    db: Session = Depends(get_db),
) -> ThemeSourceRunRead:
    run = execute_theme_source_run(db, source_id, payload)
    return serialize_theme_source_run(run)
