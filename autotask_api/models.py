from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Text, event
from sqlalchemy.orm import Mapped, mapped_column, relationship

from autotask_api.config import get_settings
from autotask_api.database import Base
from autotask_api.services.task_fields import EMPTY_DEDUP_KEY_EXPR_SENTINEL, EMPTY_TEXT_SENTINEL
from autotask_api.services.time_utils import now_shanghai


settings = get_settings()
SCHEMA = settings.db_schema


def utcnow() -> datetime:
    return now_shanghai()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class PlatformUser(TimestampMixin, Base):
    __tablename__ = "platform_user"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
    theme_topics: Mapped[list["ThemeTopic"]] = relationship(back_populates="message_template")


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


class ThemeSource(TimestampMixin, Base):
    __tablename__ = "theme_source"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('dsjfx_case_list', 'db_sql_select', 'kingbase_multi_sql')",
            name="ck_theme_source_type",
        ),
        CheckConstraint("interval_value > 0", name="ck_theme_source_interval_value"),
        CheckConstraint(
            "interval_unit IN ('minute', 'hour')",
            name="ck_theme_source_interval_unit",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source_type: Mapped[str] = mapped_column(Text, nullable=False, default="dsjfx_case_list")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    interval_value: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    interval_unit: Mapped[str] = mapped_column(Text, nullable=False, default="minute")
    timezone: Mapped[str] = mapped_column(Text, nullable=False, default="Asia/Shanghai")
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    topics: Mapped[list["ThemeTopic"]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
        order_by="ThemeTopic.priority.asc()",
    )
    runs: Mapped[list["ThemeSourceRun"]] = relationship(back_populates="source")


class ThemeTopic(TimestampMixin, Base):
    __tablename__ = "theme_topic"
    __table_args__ = (
        CheckConstraint(
            "dedup_mode IN ('permanent', 'window')",
            name="ck_theme_topic_dedup_mode",
        ),
        CheckConstraint(
            "dedup_window_minutes IS NULL OR dedup_window_minutes > 0",
            name="ck_theme_topic_dedup_window",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.theme_source.id", ondelete="CASCADE"),
        nullable=False,
    )
    theme_name: Mapped[str] = mapped_column(Text, nullable=False)
    theme_code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    message_template_id: Mapped[int | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.message_template.id")
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    filter_expr_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    dedup_mode: Mapped[str] = mapped_column(Text, nullable=False, default="permanent")
    dedup_window_minutes: Mapped[int | None] = mapped_column(Integer)
    dedup_key_template: Mapped[str] = mapped_column(Text, nullable=False, default="{event_key}")

    source: Mapped["ThemeSource"] = relationship(back_populates="topics")
    message_template: Mapped["MessageTemplate | None"] = relationship(back_populates="theme_topics")
    receiver_rules: Mapped[list["ThemeReceiverRule"]] = relationship(
        back_populates="topic",
        cascade="all, delete-orphan",
        order_by="ThemeReceiverRule.priority.asc()",
    )
    results: Mapped[list["ThemeTopicResult"]] = relationship(back_populates="topic")
    sms_logs: Mapped[list["ThemeSmsSendLog"]] = relationship(back_populates="topic")


class ThemeReceiverRule(TimestampMixin, Base):
    __tablename__ = "theme_receiver_rule"
    __table_args__ = (
        CheckConstraint(
            "rule_type IN ('fixed_receivers', 'field_match', 'field_match_with_ancestors')",
            name="ck_theme_receiver_rule_type",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.theme_topic.id", ondelete="CASCADE"),
        nullable=False,
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

    topic: Mapped["ThemeTopic"] = relationship(back_populates="receiver_rules")


class ThemeSourceRun(Base):
    __tablename__ = "theme_source_run"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.theme_source.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_no: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    send_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default=EMPTY_TEXT_SENTINEL)
    log_path: Mapped[str] = mapped_column(Text, nullable=False, default=EMPTY_TEXT_SENTINEL)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    source: Mapped["ThemeSource"] = relationship(back_populates="runs")
    results: Mapped[list["ThemeTopicResult"]] = relationship(back_populates="source_run")
    sms_logs: Mapped[list["ThemeSmsSendLog"]] = relationship(back_populates="source_run")


class ThemeTopicResult(Base):
    __tablename__ = "theme_topic_result"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(primary_key=True)
    source_run_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.theme_source_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    topic_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.theme_topic.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_key: Mapped[str] = mapped_column(Text, nullable=False)
    case_no: Mapped[str] = mapped_column(Text, nullable=False, default=EMPTY_TEXT_SENTINEL)
    raw_result_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    rendered_message: Mapped[str] = mapped_column(Text, nullable=False, default=EMPTY_TEXT_SENTINEL)
    matched_rule_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    receiver_mobiles_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    dedup_key: Mapped[str] = mapped_column(Text, nullable=False, default=EMPTY_TEXT_SENTINEL)
    oracle_eid: Mapped[str] = mapped_column(Text, nullable=False, default=EMPTY_TEXT_SENTINEL)
    send_status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    source_run: Mapped["ThemeSourceRun"] = relationship(back_populates="results")
    topic: Mapped["ThemeTopic"] = relationship(back_populates="results")
    sms_logs: Mapped[list["ThemeSmsSendLog"]] = relationship(back_populates="topic_result")


class ThemeSmsSendLog(Base):
    __tablename__ = "theme_sms_send_log"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(primary_key=True)
    source_run_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.theme_source_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    topic_result_id: Mapped[int | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.theme_topic_result.id", ondelete="SET NULL")
    )
    topic_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.theme_topic.id", ondelete="CASCADE"),
        nullable=False,
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

    source_run: Mapped["ThemeSourceRun"] = relationship(back_populates="sms_logs")
    topic_result: Mapped["ThemeTopicResult | None"] = relationship(back_populates="sms_logs")
    topic: Mapped["ThemeTopic"] = relationship(back_populates="sms_logs")


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
    remark: Mapped[str] = mapped_column(Text, nullable=False, default=EMPTY_TEXT_SENTINEL)

    phones: Mapped[list["OrgContactPhone"]] = relationship(
        back_populates="contact", cascade="all, delete-orphan", order_by="OrgContactPhone.id.asc()"
    )


def normalize_org_contact_before_flush(_mapper: Any, _connection: Any, target: OrgContact) -> None:
    if target.remark in (None, ""):
        target.remark = EMPTY_TEXT_SENTINEL


event.listen(OrgContact, "before_insert", normalize_org_contact_before_flush)
event.listen(OrgContact, "before_update", normalize_org_contact_before_flush)


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
