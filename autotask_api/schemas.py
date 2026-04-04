from __future__ import annotations

from datetime import datetime
from typing import Any
from typing import Literal

from pydantic import BaseModel, Field


class JsonPayloadMixin(BaseModel):
    model_config = {"extra": "forbid"}


class ScriptUploadResponse(BaseModel):
    script_id: int
    script_version_id: int
    script_code: str
    version_no: str
    checksum: str
    manifest: dict[str, Any]
    package_path: str


class ScriptVersionRead(BaseModel):
    id: int
    version_no: str
    package_path: str
    checksum: str
    manifest: dict[str, Any]
    change_log: str
    created_at: datetime


class ScriptRead(BaseModel):
    id: int
    script_name: str
    script_code: str
    script_type: str
    entry_file: str
    entry_func: str | None
    manifest: dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime
    versions: list[ScriptVersionRead] = Field(default_factory=list)


class MessageTemplateCreate(JsonPayloadMixin):
    template_name: str
    template_code: str
    template_content: str
    render_example: str = ""
    enabled: bool = True


class MessageTemplateUpdate(JsonPayloadMixin):
    template_name: str | None = None
    template_code: str | None = None
    template_content: str | None = None
    render_example: str | None = None
    enabled: bool | None = None


class MessageTemplateRead(BaseModel):
    id: int
    template_name: str
    template_code: str
    template_content: str
    render_example: str
    enabled: bool
    created_at: datetime
    updated_at: datetime


class TemplateRenderRequest(JsonPayloadMixin):
    variables: dict[str, Any] = Field(default_factory=dict)


class TemplateRenderResponse(BaseModel):
    rendered_text: str


class TaskScheduleUpsert(JsonPayloadMixin):
    interval_value: int
    interval_unit: Literal["minute", "hour"]
    timezone: str = "Asia/Shanghai"
    start_at: datetime | None = None
    end_at: datetime | None = None
    enabled: bool = True


class TaskCreate(JsonPayloadMixin):
    task_name: str
    script_id: int
    script_version_id: int
    message_template_id: int | None = None
    enabled: bool = True
    dedup_key_expr: str = ""
    dedup_window_minutes: int = 720
    runtime_config: dict[str, Any] = Field(default_factory=dict)
    schedule: TaskScheduleUpsert | None = None


class TaskUpdate(JsonPayloadMixin):
    task_name: str | None = None
    script_id: int | None = None
    script_version_id: int | None = None
    message_template_id: int | None = None
    enabled: bool | None = None
    dedup_key_expr: str | None = None
    dedup_window_minutes: int | None = None
    runtime_config: dict[str, Any] | None = None


class TaskScheduleRead(BaseModel):
    id: int
    interval_value: int
    interval_unit: str
    timezone: str
    start_at: datetime | None
    end_at: datetime | None
    enabled: bool
    created_at: datetime
    updated_at: datetime


class RuleBase(JsonPayloadMixin):
    rule_name: str
    rule_type: Literal["fixed_receivers", "field_match", "field_match_with_ancestors"]
    priority: int = 100
    enabled: bool = True
    source_field: str = ""
    target_table: str = "jcgkzx_autotask.org_contact"
    target_match_field: Literal["sspcsdm", "xqdm", "city_code", "county_code"] = "sspcsdm"
    target_mobile_field: str = "mobile"
    include_self: bool = True
    include_county: bool = False
    include_city: bool = False
    filter_json: dict[str, Any] = Field(default_factory=dict)
    fixed_receivers: list[str] = Field(default_factory=list)


class RuleCreate(RuleBase):
    pass


class RuleUpdate(JsonPayloadMixin):
    rule_name: str | None = None
    rule_type: Literal["fixed_receivers", "field_match", "field_match_with_ancestors"] | None = None
    priority: int | None = None
    enabled: bool | None = None
    source_field: str | None = None
    target_table: str | None = None
    target_match_field: Literal["sspcsdm", "xqdm", "city_code", "county_code"] | None = None
    target_mobile_field: str | None = None
    include_self: bool | None = None
    include_county: bool | None = None
    include_city: bool | None = None
    filter_json: dict[str, Any] | None = None
    fixed_receivers: list[str] | None = None


class RuleRead(BaseModel):
    id: int
    task_id: int
    rule_name: str
    rule_type: str
    priority: int
    enabled: bool
    source_field: str
    target_table: str
    target_match_field: str
    target_mobile_field: str
    include_self: bool
    include_county: bool
    include_city: bool
    filter_json: dict[str, Any]
    fixed_receivers: list[str]
    created_at: datetime
    updated_at: datetime


class TaskRead(BaseModel):
    id: int
    task_name: str
    script_id: int
    script_version_id: int
    message_template_id: int | None
    enabled: bool
    dedup_key_expr: str
    dedup_window_minutes: int
    runtime_config: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    schedules: list[TaskScheduleRead] = Field(default_factory=list)
    rules: list[RuleRead] = Field(default_factory=list)


class RuleTestRequest(JsonPayloadMixin):
    sample_row: dict[str, Any]


class ContactPhoneRead(BaseModel):
    id: int
    phone_raw: str
    mobile: str
    is_primary: bool
    status: str


class ContactRead(BaseModel):
    id: int
    xq: str | None
    xqdm: str | None
    sspcs: str | None
    sspcsdm: str | None
    city_code: str | None
    county_code: str | None
    unit_level: str
    xm: str | None
    zw: str | None
    rwzt: str | None
    status: str
    remark: str
    phones: list[ContactPhoneRead] = Field(default_factory=list)


class RuleTestResponse(BaseModel):
    resolved_codes: list[str]
    mobiles: list[str]
    contacts: list[ContactRead]


class ContactSearchResponse(BaseModel):
    items: list[ContactRead]
    total: int


class ThemeSourceSchedule(JsonPayloadMixin):
    interval_value: int
    interval_unit: Literal["minute", "hour"]
    timezone: str = "Asia/Shanghai"
    start_at: datetime | None = None
    end_at: datetime | None = None


class ThemeReceiverRuleBase(JsonPayloadMixin):
    rule_name: str
    rule_type: Literal["fixed_receivers", "field_match", "field_match_with_ancestors"]
    priority: int = 100
    enabled: bool = True
    source_field: str = ""
    target_table: str = "jcgkzx_autotask.org_contact"
    target_match_field: Literal["sspcsdm", "xqdm", "city_code", "county_code"] = "sspcsdm"
    target_mobile_field: str = "mobile"
    include_self: bool = True
    include_county: bool = False
    include_city: bool = False
    filter_json: dict[str, Any] = Field(default_factory=dict)
    fixed_receivers: list[str] = Field(default_factory=list)


class ThemeReceiverRuleCreate(ThemeReceiverRuleBase):
    pass


class ThemeReceiverRuleUpdate(JsonPayloadMixin):
    rule_name: str | None = None
    rule_type: Literal["fixed_receivers", "field_match", "field_match_with_ancestors"] | None = None
    priority: int | None = None
    enabled: bool | None = None
    source_field: str | None = None
    target_table: str | None = None
    target_match_field: Literal["sspcsdm", "xqdm", "city_code", "county_code"] | None = None
    target_mobile_field: str | None = None
    include_self: bool | None = None
    include_county: bool | None = None
    include_city: bool | None = None
    filter_json: dict[str, Any] | None = None
    fixed_receivers: list[str] | None = None


class ThemeReceiverRuleRead(BaseModel):
    id: int
    topic_id: int
    rule_name: str
    rule_type: str
    priority: int
    enabled: bool
    source_field: str
    target_table: str
    target_match_field: str
    target_mobile_field: str
    include_self: bool
    include_county: bool
    include_city: bool
    filter_json: dict[str, Any]
    fixed_receivers: list[str]
    created_at: datetime
    updated_at: datetime


class ThemeTopicCreate(JsonPayloadMixin):
    theme_name: str
    theme_code: str
    message_template_id: int | None = None
    enabled: bool = True
    priority: int = 100
    filter_expr: dict[str, Any] = Field(default_factory=dict)
    dedup_mode: Literal["permanent", "window"] = "permanent"
    dedup_window_minutes: int | None = None
    dedup_key_template: str = "{event_key}"


class ThemeTopicUpdate(JsonPayloadMixin):
    theme_name: str | None = None
    theme_code: str | None = None
    message_template_id: int | None = None
    enabled: bool | None = None
    priority: int | None = None
    filter_expr: dict[str, Any] | None = None
    dedup_mode: Literal["permanent", "window"] | None = None
    dedup_window_minutes: int | None = None
    dedup_key_template: str | None = None


class ThemeTopicRead(BaseModel):
    id: int
    source_id: int
    theme_name: str
    theme_code: str
    message_template_id: int | None
    enabled: bool
    priority: int
    filter_expr: dict[str, Any]
    dedup_mode: str
    dedup_window_minutes: int | None
    dedup_key_template: str
    created_at: datetime
    updated_at: datetime
    receiver_rules: list[ThemeReceiverRuleRead] = Field(default_factory=list)


class ThemeSourceCreate(JsonPayloadMixin):
    source_name: str
    source_code: str
    source_type: Literal["dsjfx_case_list"] = "dsjfx_case_list"
    enabled: bool = True
    source_config: dict[str, Any] = Field(default_factory=dict)
    schedule: ThemeSourceSchedule


class ThemeSourceUpdate(JsonPayloadMixin):
    source_name: str | None = None
    source_code: str | None = None
    source_type: Literal["dsjfx_case_list"] | None = None
    enabled: bool | None = None
    source_config: dict[str, Any] | None = None
    schedule: ThemeSourceSchedule | None = None


class ThemeSourceRead(BaseModel):
    id: int
    source_name: str
    source_code: str
    source_type: str
    enabled: bool
    source_config: dict[str, Any]
    schedule: ThemeSourceSchedule
    topic_count: int = 0
    created_at: datetime
    updated_at: datetime


class ThemeSourceDetailRead(ThemeSourceRead):
    topics: list[ThemeTopicRead] = Field(default_factory=list)


class ThemeSourceRunRequest(JsonPayloadMixin):
    dry_run: bool = True
    context_override: dict[str, Any] = Field(default_factory=dict)


class TaskRunRequest(JsonPayloadMixin):
    dry_run: bool = True
    context_override: dict[str, Any] = Field(default_factory=dict)


class TaskRunResultRead(BaseModel):
    id: int
    task_run_id: int
    event_key: str
    raw_result: dict[str, Any]
    rendered_message: str
    matched_rule_ids: list[int]
    receiver_mobiles: list[str]
    send_status: str
    created_at: datetime


class SmsSendLogRead(BaseModel):
    id: int
    task_run_id: int
    task_result_id: int | None
    mobile: str
    content: str
    provider: str
    provider_msg_id: str
    status: str
    error_message: str
    created_at: datetime


class TaskRunRead(BaseModel):
    id: int
    task_id: int
    run_no: str
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    result_count: int
    hit_count: int
    send_count: int
    error_message: str
    log_path: str
    created_at: datetime


class TaskRunDetailRead(TaskRunRead):
    results: list[TaskRunResultRead] = Field(default_factory=list)
    sms_logs: list[SmsSendLogRead] = Field(default_factory=list)


class ThemeTopicResultRead(BaseModel):
    id: int
    source_run_id: int
    topic_id: int
    event_key: str
    case_no: str
    raw_result: dict[str, Any]
    rendered_message: str
    matched_rule_ids: list[int]
    receiver_mobiles: list[str]
    dedup_key: str
    oracle_eid: str
    send_status: str
    created_at: datetime


class ThemeSmsSendLogRead(BaseModel):
    id: int
    source_run_id: int
    topic_result_id: int | None
    topic_id: int
    mobile: str
    content: str
    provider: str
    provider_msg_id: str
    status: str
    error_message: str
    created_at: datetime


class ThemeSourceRunRead(BaseModel):
    id: int
    source_id: int
    run_no: str
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    fetched_count: int
    matched_count: int
    send_count: int
    error_message: str
    log_path: str
    created_at: datetime


class ThemeSourceRunDetailRead(ThemeSourceRunRead):
    results: list[ThemeTopicResultRead] = Field(default_factory=list)
    sms_logs: list[ThemeSmsSendLogRead] = Field(default_factory=list)
