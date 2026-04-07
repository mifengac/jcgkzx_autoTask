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
    ThemeReceiverRule,
    ThemeSource,
    ThemeSourceRun,
    ThemeSmsSendLog,
    ThemeTopic,
    ThemeTopicResult,
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
    ThemeReceiverRuleRead,
    ThemeSmsSendLogDetailRead,
    ThemeSmsSendLogSummaryRead,
    ThemeSmsSendLogRead,
    ThemeSourceDetailRead,
    ThemeSourceRead,
    ThemeSourceRunRead,
    ThemeSourceSchedule,
    ThemeTopicResultDetailRead,
    ThemeTopicResultSummaryRead,
    ThemeTopicRead,
    ThemeTopicResultRead,
)
from autotask_api.services.rule_engine import parse_json_text
from autotask_api.services.task_fields import (
    normalize_dedup_key_expr_output,
    normalize_non_null_text_output,
)
from autotask_api.services.time_utils import to_shanghai_aware


def serialize_dt(value):
    return to_shanghai_aware(value)


def serialize_script_version(version: ScriptVersion) -> ScriptVersionRead:
    return ScriptVersionRead(
        id=version.id,
        version_no=version.version_no,
        package_path=version.package_path,
        checksum=version.checksum,
        manifest=parse_json_text(version.manifest_json, {}),
        change_log=version.change_log,
        created_at=serialize_dt(version.created_at),
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
        created_at=serialize_dt(script.created_at),
        updated_at=serialize_dt(script.updated_at),
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
        created_at=serialize_dt(template.created_at),
        updated_at=serialize_dt(template.updated_at),
    )


def serialize_schedule(schedule: TaskSchedule) -> TaskScheduleRead:
    return TaskScheduleRead(
        id=schedule.id,
        interval_value=schedule.interval_value,
        interval_unit=schedule.interval_unit,
        timezone=schedule.timezone,
        start_at=serialize_dt(schedule.start_at),
        end_at=serialize_dt(schedule.end_at),
        enabled=schedule.enabled,
        created_at=serialize_dt(schedule.created_at),
        updated_at=serialize_dt(schedule.updated_at),
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
        created_at=serialize_dt(rule.created_at),
        updated_at=serialize_dt(rule.updated_at),
    )


def serialize_task(task: AlertTask) -> TaskRead:
    return TaskRead(
        id=task.id,
        task_name=task.task_name,
        script_id=task.script_id,
        script_version_id=task.script_version_id,
        message_template_id=task.message_template_id,
        enabled=task.enabled,
        dedup_key_expr=normalize_dedup_key_expr_output(task.dedup_key_expr),
        dedup_window_minutes=task.dedup_window_minutes,
        runtime_config=parse_json_text(task.runtime_config_json, {}),
        created_at=serialize_dt(task.created_at),
        updated_at=serialize_dt(task.updated_at),
        schedules=[serialize_schedule(schedule) for schedule in task.schedules],
        rules=[serialize_rule(rule) for rule in task.rules],
    )


def serialize_theme_source_schedule(source: ThemeSource) -> ThemeSourceSchedule:
    return ThemeSourceSchedule(
        interval_value=source.interval_value,
        interval_unit=source.interval_unit,
        timezone=source.timezone,
        start_at=serialize_dt(source.start_at),
        end_at=serialize_dt(source.end_at),
    )


def serialize_theme_receiver_rule(rule: ThemeReceiverRule) -> ThemeReceiverRuleRead:
    return ThemeReceiverRuleRead(
        id=rule.id,
        topic_id=rule.topic_id,
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
        created_at=serialize_dt(rule.created_at),
        updated_at=serialize_dt(rule.updated_at),
    )


def serialize_theme_topic(topic: ThemeTopic) -> ThemeTopicRead:
    return ThemeTopicRead(
        id=topic.id,
        source_id=topic.source_id,
        theme_name=topic.theme_name,
        theme_code=topic.theme_code,
        message_template_id=topic.message_template_id,
        enabled=topic.enabled,
        priority=topic.priority,
        filter_expr=parse_json_text(topic.filter_expr_json, {}),
        dedup_mode=topic.dedup_mode,
        dedup_window_minutes=topic.dedup_window_minutes,
        dedup_key_template=topic.dedup_key_template,
        created_at=serialize_dt(topic.created_at),
        updated_at=serialize_dt(topic.updated_at),
        receiver_rules=[serialize_theme_receiver_rule(rule) for rule in topic.receiver_rules],
    )


def serialize_theme_source(source: ThemeSource) -> ThemeSourceRead:
    return ThemeSourceRead(
        id=source.id,
        source_name=source.source_name,
        source_code=source.source_code,
        source_type=source.source_type,
        enabled=source.enabled,
        source_config=parse_json_text(source.source_config_json, {}),
        schedule=serialize_theme_source_schedule(source),
        topic_count=len(source.topics),
        created_at=serialize_dt(source.created_at),
        updated_at=serialize_dt(source.updated_at),
    )


def serialize_theme_source_detail(source: ThemeSource) -> ThemeSourceDetailRead:
    return ThemeSourceDetailRead(
        **serialize_theme_source(source).model_dump(),
        topics=[serialize_theme_topic(topic) for topic in source.topics],
    )


def serialize_theme_source_run(run: ThemeSourceRun) -> ThemeSourceRunRead:
    return ThemeSourceRunRead(
        id=run.id,
        source_id=run.source_id,
        run_no=run.run_no,
        status=run.status,
        started_at=serialize_dt(run.started_at),
        finished_at=serialize_dt(run.finished_at),
        fetched_count=run.fetched_count,
        matched_count=run.matched_count,
        send_count=run.send_count,
        error_message=normalize_non_null_text_output(run.error_message),
        log_path=normalize_non_null_text_output(run.log_path),
        created_at=serialize_dt(run.created_at),
    )


def serialize_theme_topic_result(item: ThemeTopicResult) -> ThemeTopicResultRead:
    return ThemeTopicResultRead(
        id=item.id,
        source_run_id=item.source_run_id,
        topic_id=item.topic_id,
        event_key=item.event_key,
        case_no=normalize_non_null_text_output(item.case_no),
        raw_result=parse_json_text(item.raw_result_json, {}),
        rendered_message=normalize_non_null_text_output(item.rendered_message),
        matched_rule_ids=parse_json_text(item.matched_rule_ids_json, []),
        receiver_mobiles=parse_json_text(item.receiver_mobiles_json, []),
        dedup_key=normalize_non_null_text_output(item.dedup_key),
        oracle_eid=normalize_non_null_text_output(item.oracle_eid),
        send_status=item.send_status,
        created_at=serialize_dt(item.created_at),
    )


def serialize_theme_topic_result_summary(item: ThemeTopicResult) -> ThemeTopicResultSummaryRead:
    topic = item.topic
    source = item.source_run.source
    return ThemeTopicResultSummaryRead(
        id=item.id,
        source_run_id=item.source_run_id,
        source_id=source.id,
        source_name=source.source_name,
        topic_id=topic.id,
        topic_name=topic.theme_name,
        topic_code=topic.theme_code,
        event_key=item.event_key,
        case_no=normalize_non_null_text_output(item.case_no),
        receiver_mobiles=parse_json_text(item.receiver_mobiles_json, []),
        oracle_eid=normalize_non_null_text_output(item.oracle_eid),
        send_status=item.send_status,
        created_at=serialize_dt(item.created_at),
    )


def serialize_theme_topic_result_detail(item: ThemeTopicResult) -> ThemeTopicResultDetailRead:
    return ThemeTopicResultDetailRead(
        **serialize_theme_topic_result_summary(item).model_dump(),
        raw_result=parse_json_text(item.raw_result_json, {}),
        rendered_message=normalize_non_null_text_output(item.rendered_message),
        matched_rule_ids=parse_json_text(item.matched_rule_ids_json, []),
        dedup_key=normalize_non_null_text_output(item.dedup_key),
    )


def serialize_theme_sms_log(item: ThemeSmsSendLog) -> ThemeSmsSendLogRead:
    return ThemeSmsSendLogRead(
        id=item.id,
        source_run_id=item.source_run_id,
        topic_result_id=item.topic_result_id,
        topic_id=item.topic_id,
        mobile=item.mobile,
        content=item.content,
        provider=item.provider,
        provider_msg_id=normalize_non_null_text_output(item.provider_msg_id),
        status=item.status,
        error_message=normalize_non_null_text_output(item.error_message),
        created_at=serialize_dt(item.created_at),
    )


def serialize_theme_sms_log_summary(item: ThemeSmsSendLog) -> ThemeSmsSendLogSummaryRead:
    topic = item.topic
    source = item.source_run.source
    content = item.content or ""
    preview = content if len(content) <= 72 else f"{content[:72]}..."
    return ThemeSmsSendLogSummaryRead(
        id=item.id,
        source_run_id=item.source_run_id,
        topic_result_id=item.topic_result_id,
        source_id=source.id,
        source_name=source.source_name,
        topic_id=topic.id,
        topic_name=topic.theme_name,
        topic_code=topic.theme_code,
        mobile=item.mobile,
        content_preview=preview,
        provider=item.provider,
        provider_msg_id=normalize_non_null_text_output(item.provider_msg_id),
        status=item.status,
        error_message=normalize_non_null_text_output(item.error_message),
        created_at=serialize_dt(item.created_at),
    )


def serialize_theme_sms_log_detail(item: ThemeSmsSendLog) -> ThemeSmsSendLogDetailRead:
    topic_result = item.topic_result
    return ThemeSmsSendLogDetailRead(
        **serialize_theme_sms_log_summary(item).model_dump(),
        content=item.content,
        oracle_eid=normalize_non_null_text_output(topic_result.oracle_eid if topic_result else ""),
        result_send_status=topic_result.send_status if topic_result else "",
        receiver_mobiles=parse_json_text(topic_result.receiver_mobiles_json, []) if topic_result else [],
        raw_result=parse_json_text(topic_result.raw_result_json, {}) if topic_result else {},
    )


def serialize_contact_phone(phone: OrgContactPhone) -> ContactPhoneRead:
    return ContactPhoneRead(
        id=phone.id,
        phone_raw=phone.phone_raw,
        mobile=phone.mobile,
        is_primary=phone.is_primary,
        status=phone.status,
        created_at=serialize_dt(phone.created_at),
        updated_at=serialize_dt(phone.updated_at),
    )


def serialize_contact(contact: OrgContact) -> ContactRead:
    return ContactRead(
        id=contact.id,
        source_system=contact.source_system,
        source_pk=contact.source_pk,
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
        raw_lxdh=contact.raw_lxdh,
        status=contact.status,
        remark=normalize_non_null_text_output(contact.remark),
        created_at=serialize_dt(contact.created_at),
        updated_at=serialize_dt(contact.updated_at),
        phones=[serialize_contact_phone(phone) for phone in contact.phones],
    )
