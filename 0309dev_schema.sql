-- 0309dev_schema.sql
-- Target schema: jcgkzx_autotask
-- Note: the current MCP connection is read-only and cannot execute DDL.
-- Run this script with a writable Kingbase/PostgreSQL client.

CREATE SCHEMA IF NOT EXISTS jcgkzx_autotask;

CREATE TABLE IF NOT EXISTS jcgkzx_autotask.script_definition (
    id BIGSERIAL PRIMARY KEY,
    script_name TEXT NOT NULL,
    script_code TEXT NOT NULL,
    script_type TEXT NOT NULL DEFAULT 'python_zip',
    entry_file TEXT NOT NULL,
    entry_func TEXT,
    manifest_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_script_definition_code
    ON jcgkzx_autotask.script_definition (script_code);

CREATE TABLE IF NOT EXISTS jcgkzx_autotask.script_version (
    id BIGSERIAL PRIMARY KEY,
    script_id BIGINT NOT NULL REFERENCES jcgkzx_autotask.script_definition(id) ON DELETE CASCADE,
    version_no TEXT NOT NULL,
    package_path TEXT NOT NULL,
    checksum TEXT NOT NULL,
    manifest_json TEXT NOT NULL DEFAULT '{}',
    change_log TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_script_version_pair
    ON jcgkzx_autotask.script_version (script_id, version_no);

CREATE TABLE IF NOT EXISTS jcgkzx_autotask.message_template (
    id BIGSERIAL PRIMARY KEY,
    template_name TEXT NOT NULL,
    template_code TEXT NOT NULL,
    template_content TEXT NOT NULL,
    render_example TEXT NOT NULL DEFAULT '',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_message_template_code
    ON jcgkzx_autotask.message_template (template_code);

CREATE TABLE IF NOT EXISTS jcgkzx_autotask.alert_task (
    id BIGSERIAL PRIMARY KEY,
    task_name TEXT NOT NULL,
    script_id BIGINT NOT NULL REFERENCES jcgkzx_autotask.script_definition(id),
    script_version_id BIGINT NOT NULL REFERENCES jcgkzx_autotask.script_version(id),
    message_template_id BIGINT REFERENCES jcgkzx_autotask.message_template(id),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    dedup_key_expr TEXT NOT NULL DEFAULT '',
    dedup_window_minutes INTEGER NOT NULL DEFAULT 720,
    runtime_config_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_alert_task_dedup_window CHECK (dedup_window_minutes >= 0)
);

CREATE INDEX IF NOT EXISTS idx_alert_task_enabled
    ON jcgkzx_autotask.alert_task (enabled);

CREATE TABLE IF NOT EXISTS jcgkzx_autotask.task_schedule (
    id BIGSERIAL PRIMARY KEY,
    task_id BIGINT NOT NULL REFERENCES jcgkzx_autotask.alert_task(id) ON DELETE CASCADE,
    interval_value INTEGER NOT NULL,
    interval_unit TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
    start_at TIMESTAMPTZ,
    end_at TIMESTAMPTZ,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_task_schedule_interval_value CHECK (interval_value > 0),
    CONSTRAINT ck_task_schedule_interval_unit CHECK (interval_unit IN ('minute', 'hour'))
);

CREATE INDEX IF NOT EXISTS idx_task_schedule_task_enabled
    ON jcgkzx_autotask.task_schedule (task_id, enabled);

CREATE TABLE IF NOT EXISTS jcgkzx_autotask.task_rule (
    id BIGSERIAL PRIMARY KEY,
    task_id BIGINT NOT NULL REFERENCES jcgkzx_autotask.alert_task(id) ON DELETE CASCADE,
    rule_name TEXT NOT NULL,
    rule_type TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 100,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    source_field TEXT NOT NULL DEFAULT '',
    target_table TEXT NOT NULL DEFAULT 'jcgkzx_autotask.org_contact',
    target_match_field TEXT NOT NULL DEFAULT 'sspcsdm',
    target_mobile_field TEXT NOT NULL DEFAULT 'mobile',
    include_self BOOLEAN NOT NULL DEFAULT TRUE,
    include_county BOOLEAN NOT NULL DEFAULT FALSE,
    include_city BOOLEAN NOT NULL DEFAULT FALSE,
    filter_json TEXT NOT NULL DEFAULT '{}',
    fixed_receivers_json TEXT NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_task_rule_type CHECK (
        rule_type IN ('fixed_receivers', 'field_match', 'field_match_with_ancestors')
    )
);

CREATE INDEX IF NOT EXISTS idx_task_rule_task_enabled_priority
    ON jcgkzx_autotask.task_rule (task_id, enabled, priority);

CREATE TABLE IF NOT EXISTS jcgkzx_autotask.task_run (
    id BIGSERIAL PRIMARY KEY,
    task_id BIGINT NOT NULL REFERENCES jcgkzx_autotask.alert_task(id) ON DELETE CASCADE,
    run_no TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    result_count INTEGER NOT NULL DEFAULT 0,
    hit_count INTEGER NOT NULL DEFAULT 0,
    send_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT NOT NULL DEFAULT '',
    log_path TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_task_run_run_no
    ON jcgkzx_autotask.task_run (run_no);

CREATE INDEX IF NOT EXISTS idx_task_run_task_started
    ON jcgkzx_autotask.task_run (task_id, started_at DESC);

CREATE TABLE IF NOT EXISTS jcgkzx_autotask.task_run_result (
    id BIGSERIAL PRIMARY KEY,
    task_run_id BIGINT NOT NULL REFERENCES jcgkzx_autotask.task_run(id) ON DELETE CASCADE,
    event_key TEXT NOT NULL,
    raw_result_json TEXT NOT NULL DEFAULT '{}',
    rendered_message TEXT NOT NULL DEFAULT '',
    matched_rule_ids_json TEXT NOT NULL DEFAULT '[]',
    receiver_mobiles_json TEXT NOT NULL DEFAULT '[]',
    send_status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_task_run_result_run
    ON jcgkzx_autotask.task_run_result (task_run_id);

CREATE INDEX IF NOT EXISTS idx_task_run_result_event_key
    ON jcgkzx_autotask.task_run_result (event_key);

CREATE TABLE IF NOT EXISTS jcgkzx_autotask.sms_send_log (
    id BIGSERIAL PRIMARY KEY,
    task_run_id BIGINT NOT NULL REFERENCES jcgkzx_autotask.task_run(id) ON DELETE CASCADE,
    task_result_id BIGINT REFERENCES jcgkzx_autotask.task_run_result(id) ON DELETE SET NULL,
    mobile TEXT NOT NULL,
    content TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'oracle_gateway',
    provider_msg_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sms_send_log_run_status
    ON jcgkzx_autotask.sms_send_log (task_run_id, status);

CREATE INDEX IF NOT EXISTS idx_sms_send_log_mobile
    ON jcgkzx_autotask.sms_send_log (mobile);

CREATE TABLE IF NOT EXISTS jcgkzx_autotask.theme_source (
    id BIGSERIAL PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_code TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'dsjfx_case_list',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    interval_value INTEGER NOT NULL DEFAULT 20,
    interval_unit TEXT NOT NULL DEFAULT 'minute',
    timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
    start_at TIMESTAMPTZ,
    end_at TIMESTAMPTZ,
    source_config_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_theme_source_type CHECK (
        source_type IN ('dsjfx_case_list')
    ),
    CONSTRAINT ck_theme_source_interval_value CHECK (interval_value > 0),
    CONSTRAINT ck_theme_source_interval_unit CHECK (
        interval_unit IN ('minute', 'hour')
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_theme_source_code
    ON jcgkzx_autotask.theme_source (source_code);

CREATE INDEX IF NOT EXISTS idx_theme_source_enabled
    ON jcgkzx_autotask.theme_source (enabled);

CREATE TABLE IF NOT EXISTS jcgkzx_autotask.theme_topic (
    id BIGSERIAL PRIMARY KEY,
    source_id BIGINT NOT NULL REFERENCES jcgkzx_autotask.theme_source(id) ON DELETE CASCADE,
    theme_name TEXT NOT NULL,
    theme_code TEXT NOT NULL,
    message_template_id BIGINT REFERENCES jcgkzx_autotask.message_template(id),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    priority INTEGER NOT NULL DEFAULT 100,
    filter_expr_json TEXT NOT NULL DEFAULT '{}',
    dedup_mode TEXT NOT NULL DEFAULT 'permanent',
    dedup_window_minutes INTEGER,
    dedup_key_template TEXT NOT NULL DEFAULT '{event_key}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_theme_topic_dedup_mode CHECK (
        dedup_mode IN ('permanent', 'window')
    ),
    CONSTRAINT ck_theme_topic_dedup_window CHECK (
        dedup_window_minutes IS NULL OR dedup_window_minutes > 0
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_theme_topic_code
    ON jcgkzx_autotask.theme_topic (theme_code);

CREATE INDEX IF NOT EXISTS idx_theme_topic_source_enabled_priority
    ON jcgkzx_autotask.theme_topic (source_id, enabled, priority);

CREATE TABLE IF NOT EXISTS jcgkzx_autotask.theme_receiver_rule (
    id BIGSERIAL PRIMARY KEY,
    topic_id BIGINT NOT NULL REFERENCES jcgkzx_autotask.theme_topic(id) ON DELETE CASCADE,
    rule_name TEXT NOT NULL,
    rule_type TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 100,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    source_field TEXT NOT NULL DEFAULT '',
    target_table TEXT NOT NULL DEFAULT 'jcgkzx_autotask.org_contact',
    target_match_field TEXT NOT NULL DEFAULT 'sspcsdm',
    target_mobile_field TEXT NOT NULL DEFAULT 'mobile',
    include_self BOOLEAN NOT NULL DEFAULT TRUE,
    include_county BOOLEAN NOT NULL DEFAULT FALSE,
    include_city BOOLEAN NOT NULL DEFAULT FALSE,
    filter_json TEXT NOT NULL DEFAULT '{}',
    fixed_receivers_json TEXT NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_theme_receiver_rule_type CHECK (
        rule_type IN ('fixed_receivers', 'field_match', 'field_match_with_ancestors')
    )
);

CREATE INDEX IF NOT EXISTS idx_theme_receiver_rule_topic_enabled_priority
    ON jcgkzx_autotask.theme_receiver_rule (topic_id, enabled, priority);

CREATE TABLE IF NOT EXISTS jcgkzx_autotask.theme_source_run (
    id BIGSERIAL PRIMARY KEY,
    source_id BIGINT NOT NULL REFERENCES jcgkzx_autotask.theme_source(id) ON DELETE CASCADE,
    run_no TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    fetched_count INTEGER NOT NULL DEFAULT 0,
    matched_count INTEGER NOT NULL DEFAULT 0,
    send_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT NOT NULL DEFAULT '',
    log_path TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_theme_source_run_run_no
    ON jcgkzx_autotask.theme_source_run (run_no);

CREATE INDEX IF NOT EXISTS idx_theme_source_run_source_started
    ON jcgkzx_autotask.theme_source_run (source_id, started_at DESC);

CREATE TABLE IF NOT EXISTS jcgkzx_autotask.theme_topic_result (
    id BIGSERIAL PRIMARY KEY,
    source_run_id BIGINT NOT NULL REFERENCES jcgkzx_autotask.theme_source_run(id) ON DELETE CASCADE,
    topic_id BIGINT NOT NULL REFERENCES jcgkzx_autotask.theme_topic(id) ON DELETE CASCADE,
    event_key TEXT NOT NULL,
    case_no TEXT NOT NULL DEFAULT '',
    raw_result_json TEXT NOT NULL DEFAULT '{}',
    rendered_message TEXT NOT NULL DEFAULT '',
    matched_rule_ids_json TEXT NOT NULL DEFAULT '[]',
    receiver_mobiles_json TEXT NOT NULL DEFAULT '[]',
    dedup_key TEXT NOT NULL DEFAULT '',
    oracle_eid TEXT NOT NULL DEFAULT '',
    send_status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_theme_topic_result_run
    ON jcgkzx_autotask.theme_topic_result (source_run_id);

CREATE INDEX IF NOT EXISTS idx_theme_topic_result_topic
    ON jcgkzx_autotask.theme_topic_result (topic_id);

CREATE INDEX IF NOT EXISTS idx_theme_topic_result_event_key
    ON jcgkzx_autotask.theme_topic_result (event_key);

CREATE TABLE IF NOT EXISTS jcgkzx_autotask.theme_sms_send_log (
    id BIGSERIAL PRIMARY KEY,
    source_run_id BIGINT NOT NULL REFERENCES jcgkzx_autotask.theme_source_run(id) ON DELETE CASCADE,
    topic_result_id BIGINT REFERENCES jcgkzx_autotask.theme_topic_result(id) ON DELETE SET NULL,
    topic_id BIGINT NOT NULL REFERENCES jcgkzx_autotask.theme_topic(id) ON DELETE CASCADE,
    mobile TEXT NOT NULL,
    content TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'oracle_gateway',
    provider_msg_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_theme_sms_send_log_run_status
    ON jcgkzx_autotask.theme_sms_send_log (source_run_id, status);

CREATE INDEX IF NOT EXISTS idx_theme_sms_send_log_topic
    ON jcgkzx_autotask.theme_sms_send_log (topic_id);

CREATE INDEX IF NOT EXISTS idx_theme_sms_send_log_mobile
    ON jcgkzx_autotask.theme_sms_send_log (mobile);

CREATE TABLE IF NOT EXISTS jcgkzx_autotask.org_contact (
    id BIGSERIAL PRIMARY KEY,
    source_system TEXT NOT NULL DEFAULT 'ywdata.b_dxpt_mdjfyj',
    source_pk TEXT,
    xq TEXT,
    xqdm TEXT,
    sspcs TEXT,
    sspcsdm TEXT,
    city_code TEXT,
    county_code TEXT,
    unit_level TEXT NOT NULL DEFAULT 'unknown',
    xm TEXT,
    zw TEXT,
    rwzt TEXT,
    raw_lxdh TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    remark TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_org_contact_unit_level CHECK (
        unit_level IN ('city', 'county', 'station', 'unknown')
    ),
    CONSTRAINT ck_org_contact_status CHECK (
        status IN ('active', 'inactive')
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_org_contact_source_pk
    ON jcgkzx_autotask.org_contact (source_system, source_pk)
    WHERE source_pk IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_org_contact_sspcsdm_status
    ON jcgkzx_autotask.org_contact (sspcsdm, status);

CREATE INDEX IF NOT EXISTS idx_org_contact_xqdm_status
    ON jcgkzx_autotask.org_contact (xqdm, status);

CREATE INDEX IF NOT EXISTS idx_org_contact_rwzt
    ON jcgkzx_autotask.org_contact (rwzt);

CREATE INDEX IF NOT EXISTS idx_org_contact_county_code
    ON jcgkzx_autotask.org_contact (county_code);

CREATE INDEX IF NOT EXISTS idx_org_contact_city_code
    ON jcgkzx_autotask.org_contact (city_code);

CREATE TABLE IF NOT EXISTS jcgkzx_autotask.org_contact_phone (
    id BIGSERIAL PRIMARY KEY,
    contact_id BIGINT NOT NULL REFERENCES jcgkzx_autotask.org_contact(id) ON DELETE CASCADE,
    phone_raw TEXT NOT NULL,
    mobile TEXT NOT NULL,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_org_contact_phone_status CHECK (
        status IN ('active', 'inactive')
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_org_contact_phone_pair
    ON jcgkzx_autotask.org_contact_phone (contact_id, mobile);

CREATE INDEX IF NOT EXISTS idx_org_contact_phone_mobile
    ON jcgkzx_autotask.org_contact_phone (mobile, status);

CREATE INDEX IF NOT EXISTS idx_org_contact_phone_contact
    ON jcgkzx_autotask.org_contact_phone (contact_id, status);

CREATE OR REPLACE VIEW jcgkzx_autotask.b_dxpt_mdjfyj AS
SELECT
    CASE
        WHEN oc.source_pk ~ '^\d+$' THEN oc.source_pk::INTEGER
        ELSE NULL
    END AS xh,
    oc.xq,
    oc.xqdm,
    oc.sspcs,
    oc.sspcsdm,
    oc.xm,
    oc.zw,
    STRING_AGG(ocp.mobile, ',' ORDER BY ocp.is_primary DESC, ocp.mobile) AS lxdh,
    oc.remark AS bz,
    oc.created_at AS lrsj,
    oc.rwzt
FROM jcgkzx_autotask.org_contact oc
LEFT JOIN jcgkzx_autotask.org_contact_phone ocp
    ON ocp.contact_id = oc.id
   AND ocp.status = 'active'
GROUP BY
    oc.source_pk,
    oc.xq,
    oc.xqdm,
    oc.sspcs,
    oc.sspcsdm,
    oc.xm,
    oc.zw,
    oc.remark,
    oc.created_at,
    oc.rwzt;
