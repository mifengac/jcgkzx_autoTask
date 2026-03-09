from __future__ import annotations

from typing import Any

from autotask_api.models import (
    AlertTask,
    MessageTemplate,
    OrgContact,
    OrgContactPhone,
    ScriptDefinition,
    ScriptVersion,
    TaskRule,
    TaskSchedule,
)
from autotask_api.schemas import (
    ContactPhoneRead,
    ContactRead,
    MessageTemplateRead,
    RuleRead,
    ScriptRead,
    ScriptVersionRead,
    TaskRead,
    TaskScheduleRead,
)
from autotask_api.services.rule_engine import parse_json_text


def serialize_script_version(version: ScriptVersion) -> ScriptVersionRead:
    return ScriptVersionRead(
        id=version.id,
        version_no=version.version_no,
        package_path=version.package_path,
        checksum=version.checksum,
        manifest=parse_json_text(version.manifest_json, {}),
        change_log=version.change_log,
        created_at=version.created_at,
    )


def serialize_script(script: ScriptDefinition) -> ScriptRead:
    return ScriptRead(
        id=script.id,
        script_name=script.script_name,
        script_code=script.script_code,
        script_type=script.script_type,
        entry_file=script.entry_file,
        entry_func=script.entry_func,
        manifest=parse_json_text(script.manifest_json, {}),
        status=script.status,
        created_at=script.created_at,
        updated_at=script.updated_at,
        versions=[serialize_script_version(version) for version in script.versions],
    )


def serialize_template(template: MessageTemplate) -> MessageTemplateRead:
    return MessageTemplateRead(
        id=template.id,
        template_name=template.template_name,
        template_code=template.template_code,
        template_content=template.template_content,
        render_example=template.render_example,
        enabled=template.enabled,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


def serialize_schedule(schedule: TaskSchedule) -> TaskScheduleRead:
    return TaskScheduleRead(
        id=schedule.id,
        interval_value=schedule.interval_value,
        interval_unit=schedule.interval_unit,
        timezone=schedule.timezone,
        start_at=schedule.start_at,
        end_at=schedule.end_at,
        enabled=schedule.enabled,
        created_at=schedule.created_at,
        updated_at=schedule.updated_at,
    )


def serialize_rule(rule: TaskRule) -> RuleRead:
    return RuleRead(
        id=rule.id,
        task_id=rule.task_id,
        rule_name=rule.rule_name,
        rule_type=rule.rule_type,
        priority=rule.priority,
        enabled=rule.enabled,
        source_field=rule.source_field,
        target_table=rule.target_table,
        target_match_field=rule.target_match_field,
        target_mobile_field=rule.target_mobile_field,
        include_self=rule.include_self,
        include_county=rule.include_county,
        include_city=rule.include_city,
        filter_json=parse_json_text(rule.filter_json, {}),
        fixed_receivers=parse_json_text(rule.fixed_receivers_json, []),
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


def serialize_task(task: AlertTask) -> TaskRead:
    return TaskRead(
        id=task.id,
        task_name=task.task_name,
        script_id=task.script_id,
        script_version_id=task.script_version_id,
        message_template_id=task.message_template_id,
        enabled=task.enabled,
        dedup_key_expr=task.dedup_key_expr,
        dedup_window_minutes=task.dedup_window_minutes,
        runtime_config=parse_json_text(task.runtime_config_json, {}),
        created_at=task.created_at,
        updated_at=task.updated_at,
        schedules=[serialize_schedule(schedule) for schedule in task.schedules],
        rules=[serialize_rule(rule) for rule in task.rules],
    )


def serialize_contact_phone(phone: OrgContactPhone) -> ContactPhoneRead:
    return ContactPhoneRead(
        id=phone.id,
        phone_raw=phone.phone_raw,
        mobile=phone.mobile,
        is_primary=phone.is_primary,
        status=phone.status,
    )


def serialize_contact(contact: OrgContact) -> ContactRead:
    return ContactRead(
        id=contact.id,
        xq=contact.xq,
        xqdm=contact.xqdm,
        sspcs=contact.sspcs,
        sspcsdm=contact.sspcsdm,
        city_code=contact.city_code,
        county_code=contact.county_code,
        unit_level=contact.unit_level,
        xm=contact.xm,
        zw=contact.zw,
        rwzt=contact.rwzt,
        status=contact.status,
        remark=contact.remark,
        phones=[serialize_contact_phone(phone) for phone in contact.phones],
    )
