-- 0404_theme_monitor_schema.sql
-- Incremental schema for theme-source / theme-topic monitoring.
-- Run after 0309dev_schema.sql on a writable Kingbase/PostgreSQL client.

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
    CONSTRAINT ck_theme_source_type CHECK (source_type IN ('dsjfx_case_list')),
    CONSTRAINT ck_theme_source_interval_value CHECK (interval_value > 0),
    CONSTRAINT ck_theme_source_interval_unit CHECK (interval_unit IN ('minute', 'hour'))
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
    CONSTRAINT ck_theme_topic_dedup_mode CHECK (dedup_mode IN ('permanent', 'window')),
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
