from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from autotask_api.config import get_settings
from autotask_api.database import Base
from autotask_api.services.task_fields import EMPTY_DEDUP_KEY_EXPR_SENTINEL, EMPTY_TEXT_SENTINEL


settings = get_settings()
SCHEMA = settings.db_schema
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def utcnow() -> datetime:
    return datetime.now(SHANGHAI_TZ)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class ScriptDefinition(TimestampMixin, Base):
    __tablename__ = "script_definition"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(primary_key=True)
    script_name: Mapped[str] = mapped_column(Text, nullable=False)
    script_code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    script_type: Mapped[str] = mapped_column(Text, nullable=False, default="python_zip")
    entry_file: Mapped[str] = mapped_column(Text, nullable=False)
    entry_func: Mapped[str | None] = mapped_column(Text)
    manifest_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")

    versions: Mapped[list["ScriptVersion"]] = relationship(
        back_populates="script", cascade="all, delete-orphan", order_by="ScriptVersion.id.desc()"
    )
    tasks: Mapped[list["AlertTask"]] = relationship(back_populates="script")


class ScriptVersion(Base):
    __tablename__ = "script_version"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(primary_key=True)
    script_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.script_definition.id", ondelete="CASCADE"), nullable=False
    )
    version_no: Mapped[str] = mapped_column(Text, nullable=False)
    package_path: Mapped[str] = mapped_column(Text, nullable=False)
    checksum: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    change_log: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    script: Mapped["ScriptDefinition"] = relationship(back_populates="versions")
    tasks: Mapped[list["AlertTask"]] = relationship(back_populates="script_version")


class MessageTemplate(TimestampMixin, Base):
    __tablename__ = "message_template"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(primary_key=True)
    template_name: Mapped[str] = mapped_column(Text, nullable=False)
    template_code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    template_content: Mapped[str] = mapped_column(Text, nullable=False)
    render_example: Mapped[str] = mapped_column(Text, nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    tasks: Mapped[list["AlertTask"]] = relationship(back_populates="message_template")


class AlertTask(TimestampMixin, Base):
    __tablename__ = "alert_task"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(primary_key=True)
    task_name: Mapped[str] = mapped_column(Text, nullable=False)
    script_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.script_definition.id"), nullable=False
    )
    script_version_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.script_version.id"), nullable=False
    )
    message_template_id: Mapped[int | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.message_template.id")
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    dedup_key_expr: Mapped[str] = mapped_column(
        Text, nullable=False, default=EMPTY_DEDUP_KEY_EXPR_SENTINEL
    )
    dedup_window_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=720)
    runtime_config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    script: Mapped["ScriptDefinition"] = relationship(back_populates="tasks")
    script_version: Mapped["ScriptVersion"] = relationship(back_populates="tasks")
    message_template: Mapped["MessageTemplate | None"] = relationship(back_populates="tasks")
    schedules: Mapped[list["TaskSchedule"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="TaskSchedule.id.desc()"
    )
    rules: Mapped[list["TaskRule"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="TaskRule.priority.asc()"
    )
    runs: Mapped[list["TaskRun"]] = relationship(back_populates="task")


class TaskSchedule(TimestampMixin, Base):
    __tablename__ = "task_schedule"
    __table_args__ = (
        CheckConstraint("interval_value > 0", name="ck_task_schedule_interval_value"),
        CheckConstraint(
            "interval_unit IN ('minute', 'hour')", name="ck_task_schedule_interval_unit"
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.alert_task.id", ondelete="CASCADE"), nullable=False
    )
    interval_value: Mapped[int] = mapped_column(Integer, nullable=False)
    interval_unit: Mapped[str] = mapped_column(Text, nullable=False)
    timezone: Mapped[str] = mapped_column(Text, nullable=False, default="Asia/Shanghai")
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    task: Mapped["AlertTask"] = relationship(back_populates="schedules")


class TaskRule(TimestampMixin, Base):
    __tablename__ = "task_rule"
    __table_args__ = (
        CheckConstraint(
            "rule_type IN ('fixed_receivers', 'field_match', 'field_match_with_ancestors')",
            name="ck_task_rule_type",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.alert_task.id", ondelete="CASCADE"), nullable=False
    )
    rule_name: Mapped[str] = mapped_column(Text, nullable=False)
    rule_type: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source_field: Mapped[str] = mapped_column(Text, nullable=False, default="")
    target_table: Mapped[str] = mapped_column(Text, nullable=False, default=f"{SCHEMA}.org_contact")
    target_match_field: Mapped[str] = mapped_column(Text, nullable=False, default="sspcsdm")
    target_mobile_field: Mapped[str] = mapped_column(Text, nullable=False, default="mobile")
    include_self: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    include_county: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    include_city: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    filter_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    fixed_receivers_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    task: Mapped["AlertTask"] = relationship(back_populates="rules")


class TaskRun(Base):
    __tablename__ = "task_run"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.alert_task.id", ondelete="CASCADE"), nullable=False
    )
    run_no: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    send_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default=EMPTY_TEXT_SENTINEL)
    log_path: Mapped[str] = mapped_column(Text, nullable=False, default=EMPTY_TEXT_SENTINEL)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    task: Mapped["AlertTask"] = relationship(back_populates="runs")
    results: Mapped[list["TaskRunResult"]] = relationship(back_populates="task_run")
    sms_logs: Mapped[list["SmsSendLog"]] = relationship(back_populates="task_run")


class TaskRunResult(Base):
    __tablename__ = "task_run_result"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(primary_key=True)
    task_run_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.task_run.id", ondelete="CASCADE"), nullable=False
    )
    event_key: Mapped[str] = mapped_column(Text, nullable=False)
    raw_result_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    rendered_message: Mapped[str] = mapped_column(Text, nullable=False, default=EMPTY_TEXT_SENTINEL)
    matched_rule_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    receiver_mobiles_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    send_status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    task_run: Mapped["TaskRun"] = relationship(back_populates="results")
    sms_logs: Mapped[list["SmsSendLog"]] = relationship(back_populates="task_result")


class SmsSendLog(Base):
    __tablename__ = "sms_send_log"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(primary_key=True)
    task_run_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.task_run.id", ondelete="CASCADE"), nullable=False
    )
    task_result_id: Mapped[int | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.task_run_result.id", ondelete="SET NULL")
    )
    mobile: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False, default="oracle_gateway")
    provider_msg_id: Mapped[str] = mapped_column(Text, nullable=False, default=EMPTY_TEXT_SENTINEL)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default=EMPTY_TEXT_SENTINEL)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    task_run: Mapped["TaskRun"] = relationship(back_populates="sms_logs")
    task_result: Mapped["TaskRunResult | None"] = relationship(back_populates="sms_logs")


class OrgContact(TimestampMixin, Base):
    __tablename__ = "org_contact"
    __table_args__ = (
        CheckConstraint(
            "unit_level IN ('city', 'county', 'station', 'unknown')",
            name="ck_org_contact_unit_level",
        ),
        CheckConstraint("status IN ('active', 'inactive')", name="ck_org_contact_status"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_system: Mapped[str] = mapped_column(
        Text, nullable=False, default="ywdata.b_dxpt_mdjfyj"
    )
    source_pk: Mapped[str | None] = mapped_column(Text)
    xq: Mapped[str | None] = mapped_column(Text)
    xqdm: Mapped[str | None] = mapped_column(Text)
    sspcs: Mapped[str | None] = mapped_column(Text)
    sspcsdm: Mapped[str | None] = mapped_column(Text)
    city_code: Mapped[str | None] = mapped_column(Text)
    county_code: Mapped[str | None] = mapped_column(Text)
    unit_level: Mapped[str] = mapped_column(Text, nullable=False, default="unknown")
    xm: Mapped[str | None] = mapped_column(Text)
    zw: Mapped[str | None] = mapped_column(Text)
    rwzt: Mapped[str | None] = mapped_column(Text)
    raw_lxdh: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    remark: Mapped[str] = mapped_column(Text, nullable=False, default="")

    phones: Mapped[list["OrgContactPhone"]] = relationship(
        back_populates="contact", cascade="all, delete-orphan", order_by="OrgContactPhone.id.asc()"
    )


class OrgContactPhone(TimestampMixin, Base):
    __tablename__ = "org_contact_phone"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'inactive')", name="ck_org_contact_phone_status"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    contact_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.org_contact.id", ondelete="CASCADE"), nullable=False
    )
    phone_raw: Mapped[str] = mapped_column(Text, nullable=False)
    mobile: Mapped[str] = mapped_column(Text, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")

    contact: Mapped["OrgContact"] = relationship(back_populates="phones")
