from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from autotask_api.models import (
    AlertTask,
    MessageTemplate,
    SmsSendLog,
    TaskRun,
    TaskRunResult,
)
from autotask_api.schemas import TaskRunRequest
from autotask_api.config import get_settings
from autotask_api.services.rule_engine import (
    dump_json_text,
    parse_json_text,
    render_template,
    resolve_rule_mobiles,
)
from autotask_api.services.script_runner import execute_script
from autotask_api.services.sms_gateway_client import SmsGatewayClient
from autotask_api.services.task_fields import normalize_non_null_text_input
from autotask_api.services.time_utils import now_shanghai


settings = get_settings()


def load_task_for_execution(db: Session, task_id: int) -> AlertTask:
    stmt = (
        select(AlertTask)
        .options(
            selectinload(AlertTask.script),
            selectinload(AlertTask.script_version),
            selectinload(AlertTask.message_template),
            selectinload(AlertTask.rules),
        )
        .where(AlertTask.id == task_id)
    )
    task = db.scalar(stmt)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    return task


def build_event_key(row: dict[str, Any], index: int) -> str:
    for key in ("event_id", "event_key", "case_no", "caseNo", "systemid", "id"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return f"row_{index}"


def build_message(task: AlertTask, row: dict[str, Any]) -> str:
    template: MessageTemplate | None = task.message_template
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


def create_run_record(db: Session, task: AlertTask) -> TaskRun:
    run = TaskRun(
        task_id=task.id,
        run_no=f"{task.id}_{uuid4().hex}",
        status="running",
        started_at=now_shanghai(),
        error_message=normalize_non_null_text_input(""),
        log_path=normalize_non_null_text_input(""),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def record_sms_log(
    db: Session,
    *,
    run_id: int,
    result_id: int | None,
    mobile: str,
    content: str,
    provider: str,
    status_text: str,
    error_message: str = "",
    provider_msg_id: str = "",
) -> None:
    log = SmsSendLog(
        task_run_id=run_id,
        task_result_id=result_id,
        mobile=mobile,
        content=content,
        provider=provider,
        provider_msg_id=normalize_non_null_text_input(provider_msg_id),
        status=status_text,
        error_message=normalize_non_null_text_input(error_message),
    )
    db.add(log)


def execute_task_run(db: Session, task_id: int, payload: TaskRunRequest) -> TaskRun:
    task = load_task_for_execution(db, task_id)
    if not task.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Task is disabled.",
        )

    run = create_run_record(db, task)
    runtime_config = parse_json_text(task.runtime_config_json, {})
    context = {
        "task": {
            "id": task.id,
            "task_name": task.task_name,
            "script_code": task.script.script_code,
            "script_version": task.script_version.version_no,
        },
        "runtime_config": runtime_config,
        "trigger": "manual",
        "dry_run": payload.dry_run,
        "now": now_shanghai().isoformat(),
    }
    if payload.context_override:
        context["context_override"] = payload.context_override
        runtime_config = {**runtime_config, **payload.context_override}
        context["runtime_config"] = runtime_config

    gateway: SmsGatewayClient | None = None
    provider_name = SmsGatewayClient.provider_name
    disable_sms = str(runtime_config.get("disable_sms", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    } or str(runtime_config.get("disable_send", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    try:
        rows = execute_script(script=task.script, version=task.script_version, context=context)
        sent_count = 0
        hit_count = 0

        for index, row in enumerate(rows, start=1):
            event_key = build_event_key(row, index)
            rendered_message = build_message(task, row)
            matched_rule_ids: list[int] = []
            aggregated_mobiles: list[str] = []

            for rule in sorted(task.rules, key=lambda item: item.priority):
                if not rule.enabled:
                    continue
                _, mobiles, _ = resolve_rule_mobiles(db, rule, row)
                if mobiles:
                    matched_rule_ids.append(rule.id)
                    for mobile in mobiles:
                        if mobile not in aggregated_mobiles:
                            aggregated_mobiles.append(mobile)

            result = TaskRunResult(
                task_run_id=run.id,
                event_key=event_key,
                raw_result_json=dump_json_text(row),
                rendered_message=normalize_non_null_text_input(rendered_message),
                matched_rule_ids_json=dump_json_text(matched_rule_ids),
                receiver_mobiles_json=dump_json_text(aggregated_mobiles),
                send_status="pending",
            )
            db.add(result)
            db.flush()

            if aggregated_mobiles:
                hit_count += 1

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
                    record_sms_log(
                        db,
                        run_id=run.id,
                        result_id=result.id,
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
                gateway = SmsGatewayClient()
            biz = gateway.resolve_biz(runtime_config)
            sent_for_row = 0
            failed_for_row = False

            for mobile in aggregated_mobiles:
                try:
                    outcome = gateway.send_one(
                        mobile=mobile,
                        content=rendered_message,
                        eid=event_key,
                        biz=biz,
                        dedup_minutes=settings.sms_gateway_permanent_dedup_hours * 60,
                    )
                    if outcome.status == "sent":
                        sent_for_row += 1
                        sent_count += 1
                    elif outcome.status == "failed":
                        failed_for_row = True
                    record_sms_log(
                        db,
                        run_id=run.id,
                        result_id=result.id,
                        mobile=mobile,
                        content=rendered_message,
                        provider=provider_name,
                        status_text=outcome.status,
                        error_message=outcome.error_message or "",
                    )
                except HTTPException as exc:
                    failed_for_row = True
                    record_sms_log(
                        db,
                        run_id=run.id,
                        result_id=result.id,
                        mobile=mobile,
                        content=rendered_message,
                        provider=provider_name,
                        status_text="failed",
                        error_message=str(exc.detail),
                    )

            if sent_for_row and not failed_for_row:
                result.send_status = "sent"
            elif sent_for_row and failed_for_row:
                result.send_status = "partial_failed"
            elif failed_for_row:
                result.send_status = "failed"
            else:
                # All mobiles were skipped_duplicate (or empty after filtering).
                result.send_status = "skipped_duplicate"
            db.add(result)
            db.commit()

        run.result_count = len(rows)
        run.hit_count = hit_count
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
