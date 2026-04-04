from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from autotask_api.models import (
    MessageTemplate,
    ThemeSource,
    ThemeSourceRun,
    ThemeSmsSendLog,
    ThemeTopic,
    ThemeTopicResult,
)
from autotask_api.schemas import ThemeSourceRunRequest
from autotask_api.services.oracle_sms import OracleSmsGateway
from autotask_api.services.rule_engine import (
    dump_json_text,
    parse_json_text,
    render_template,
    resolve_rule_mobiles,
)
from autotask_api.services.task_fields import (
    normalize_non_null_text_input,
    normalize_non_null_text_output,
)
from autotask_api.services.theme_adapters import get_theme_source_adapter
from autotask_api.services.theme_filter_engine import matches_filter_expr


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def now_shanghai() -> datetime:
    return datetime.now(SHANGHAI_TZ)


def load_theme_source_for_execution(db: Session, source_id: int) -> ThemeSource:
    stmt = (
        select(ThemeSource)
        .options(
            selectinload(ThemeSource.topics).selectinload(ThemeTopic.message_template),
            selectinload(ThemeSource.topics).selectinload(ThemeTopic.receiver_rules),
        )
        .where(ThemeSource.id == source_id)
    )
    source = db.scalar(stmt)
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Theme source not found.")
    return source


def create_theme_run_record(db: Session, source: ThemeSource) -> ThemeSourceRun:
    run = ThemeSourceRun(
        source_id=source.id,
        run_no=f"theme_{source.id}_{uuid4().hex}",
        status="running",
        started_at=now_shanghai(),
        error_message=normalize_non_null_text_input(""),
        log_path=normalize_non_null_text_input(""),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def record_theme_sms_log(
    db: Session,
    *,
    source_run_id: int,
    topic_result_id: int | None,
    topic_id: int,
    mobile: str,
    content: str,
    provider: str,
    status_text: str,
    error_message: str = "",
    provider_msg_id: str = "",
) -> None:
    log = ThemeSmsSendLog(
        source_run_id=source_run_id,
        topic_result_id=topic_result_id,
        topic_id=topic_id,
        mobile=mobile,
        content=content,
        provider=provider,
        provider_msg_id=normalize_non_null_text_input(provider_msg_id),
        status=status_text,
        error_message=normalize_non_null_text_input(error_message),
    )
    db.add(log)


def build_theme_message(topic: ThemeTopic, row: dict[str, Any]) -> str:
    template: MessageTemplate | None = topic.message_template
    if template:
        variables = dict(row)
        extra_vars = row.get("message_vars")
        if isinstance(extra_vars, dict):
            variables.update(extra_vars)
        return render_template(template.template_content, variables)

    for key in ("message_text", "content", "sms_content"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return dump_json_text(row)


def build_theme_dedup_key(topic: ThemeTopic, row: dict[str, Any]) -> str:
    variables = dict(row)
    extra_vars = row.get("message_vars")
    if isinstance(extra_vars, dict):
        variables.update(extra_vars)
    rendered = render_template(topic.dedup_key_template, variables).strip()
    return rendered or str(row.get("event_key") or row.get("event_id") or uuid4().hex)


def build_theme_oracle_eid(topic: ThemeTopic, dedup_key: str) -> str:
    return f"{topic.theme_code}:{dedup_key}"


def theme_dedup_since(topic: ThemeTopic, current_time: datetime) -> datetime | None:
    if topic.dedup_mode != "window":
        return None
    if not topic.dedup_window_minutes:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                f"Theme topic {topic.theme_code} uses dedup_mode=window "
                "but dedup_window_minutes is empty."
            ),
        )
    since = current_time - timedelta(minutes=topic.dedup_window_minutes)
    return since.replace(tzinfo=None)


def execute_theme_source_run(
    db: Session,
    source_id: int,
    payload: ThemeSourceRunRequest,
) -> ThemeSourceRun:
    source = load_theme_source_for_execution(db, source_id)
    if not source.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Theme source is disabled.",
        )

    run = create_theme_run_record(db, source)
    source_config = parse_json_text(source.source_config_json, {})
    if payload.context_override:
        source_config = {**source_config, **payload.context_override}

    disable_sms = str(source_config.get("disable_sms", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    } or str(source_config.get("disable_send", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    gateway: OracleSmsGateway | None = None
    provider_name = OracleSmsGateway.provider_name
    current_time = now_shanghai()

    try:
        adapter = get_theme_source_adapter(source.source_type)
        rows = adapter.fetch(
            source=source,
            source_config=source_config,
            now=current_time,
            dry_run=payload.dry_run,
        )

        matched_count = 0
        sent_count = 0

        for row in rows:
            for topic in source.topics:
                if not topic.enabled:
                    continue
                filter_expr = parse_json_text(topic.filter_expr_json, {})
                if not matches_filter_expr(row, filter_expr):
                    continue

                matched_count += 1
                rendered_message = build_theme_message(topic, row)
                matched_rule_ids: list[int] = []
                aggregated_mobiles: list[str] = []

                for rule in topic.receiver_rules:
                    if not rule.enabled:
                        continue
                    _, mobiles, _ = resolve_rule_mobiles(db, rule, row)
                    if not mobiles:
                        continue
                    matched_rule_ids.append(rule.id)
                    for mobile in mobiles:
                        if mobile not in aggregated_mobiles:
                            aggregated_mobiles.append(mobile)

                dedup_key = build_theme_dedup_key(topic, row)
                oracle_eid = build_theme_oracle_eid(topic, dedup_key)
                case_no = normalize_non_null_text_input(
                    str(row.get("case_no") or row.get("caseNo") or "")
                )
                result = ThemeTopicResult(
                    source_run_id=run.id,
                    topic_id=topic.id,
                    event_key=str(row.get("event_key") or row.get("event_id") or dedup_key),
                    case_no=case_no,
                    raw_result_json=dump_json_text(row),
                    rendered_message=normalize_non_null_text_input(rendered_message),
                    matched_rule_ids_json=dump_json_text(matched_rule_ids),
                    receiver_mobiles_json=dump_json_text(aggregated_mobiles),
                    dedup_key=normalize_non_null_text_input(dedup_key),
                    oracle_eid=normalize_non_null_text_input(oracle_eid),
                    send_status="pending",
                )
                db.add(result)
                db.flush()

                if not aggregated_mobiles:
                    result.send_status = "skipped_no_receivers"
                    db.add(result)
                    db.commit()
                    continue

                if disable_sms:
                    result.send_status = "skipped_sms_disabled"
                    db.add(result)
                    db.commit()
                    continue

                if payload.dry_run:
                    for mobile in aggregated_mobiles:
                        record_theme_sms_log(
                            db,
                            source_run_id=run.id,
                            topic_result_id=result.id,
                            topic_id=topic.id,
                            mobile=mobile,
                            content=rendered_message,
                            provider=provider_name,
                            status_text="dry_run",
                        )
                    result.send_status = "dry_run"
                    db.add(result)
                    db.commit()
                    continue

                if gateway is None:
                    gateway = OracleSmsGateway()
                credentials = gateway.resolve_credentials(source_config)
                sent_for_result = 0
                failed_for_result = False
                since = theme_dedup_since(topic, current_time)

                for mobile in aggregated_mobiles:
                    try:
                        if gateway.check_duplicate(eid=oracle_eid, mobile=mobile, since=since):
                            record_theme_sms_log(
                                db,
                                source_run_id=run.id,
                                topic_result_id=result.id,
                                topic_id=topic.id,
                                mobile=mobile,
                                content=rendered_message,
                                provider=provider_name,
                                status_text="skipped_duplicate",
                            )
                            continue

                        gateway.enqueue_sms(
                            mobile=mobile,
                            content=rendered_message,
                            eid=oracle_eid,
                            credentials=credentials,
                        )
                        sent_for_result += 1
                        sent_count += 1
                        record_theme_sms_log(
                            db,
                            source_run_id=run.id,
                            topic_result_id=result.id,
                            topic_id=topic.id,
                            mobile=mobile,
                            content=rendered_message,
                            provider=provider_name,
                            status_text="sent",
                        )
                    except HTTPException as exc:
                        failed_for_result = True
                        record_theme_sms_log(
                            db,
                            source_run_id=run.id,
                            topic_result_id=result.id,
                            topic_id=topic.id,
                            mobile=mobile,
                            content=rendered_message,
                            provider=provider_name,
                            status_text="failed",
                            error_message=str(exc.detail),
                        )

                if sent_for_result and not failed_for_result:
                    result.send_status = "sent"
                elif sent_for_result and failed_for_result:
                    result.send_status = "partial_failed"
                elif failed_for_result:
                    result.send_status = "failed"
                else:
                    result.send_status = "skipped_duplicate"

                db.add(result)
                db.commit()

        run.fetched_count = len(rows)
        run.matched_count = matched_count
        run.send_count = sent_count
        run.status = "completed" if not payload.dry_run else "completed_dry_run"
        run.finished_at = now_shanghai()
        run.error_message = normalize_non_null_text_input("")
        db.add(run)
        db.commit()
        db.refresh(run)
        return run
    except Exception as exc:
        db.rollback()
        run.status = "failed"
        run.finished_at = now_shanghai()
        run.error_message = normalize_non_null_text_input(str(exc))
        db.add(run)
        db.commit()
        db.refresh(run)
        raise


def describe_theme_result(result: ThemeTopicResult) -> str:
    return (
        f"topic_id={result.topic_id} event_key={result.event_key} "
        f"status={result.send_status} dedup_key={normalize_non_null_text_output(result.dedup_key)}"
    )
