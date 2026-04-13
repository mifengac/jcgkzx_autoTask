-- 0408_b_count.sql
-- Add b_count and table_tj(schema_name) to jcgkzx_autotask for existing deployments.

CREATE SCHEMA IF NOT EXISTS jcgkzx_autotask;

CREATE TABLE IF NOT EXISTS jcgkzx_autotask.b_count (
    bm VARCHAR NULL,
    bzw VARCHAR NULL,
    zs VARCHAR NULL,
    gxsj TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE jcgkzx_autotask.platform_user IS U&'\5E73\53F0\7528\6237\8868';
COMMENT ON TABLE jcgkzx_autotask.script_definition IS U&'\811A\672C\5B9A\4E49\8868';
COMMENT ON TABLE jcgkzx_autotask.script_version IS U&'\811A\672C\7248\672C\8868';
COMMENT ON TABLE jcgkzx_autotask.message_template IS U&'\77ED\4FE1\6A21\677F\8868';
COMMENT ON TABLE jcgkzx_autotask.alert_task IS U&'\81EA\52A8\4EFB\52A1\8868';
COMMENT ON TABLE jcgkzx_autotask.task_schedule IS U&'\4EFB\52A1\8C03\5EA6\8868';
COMMENT ON TABLE jcgkzx_autotask.task_rule IS U&'\4EFB\52A1\63A5\6536\89C4\5219\8868';
COMMENT ON TABLE jcgkzx_autotask.task_run IS U&'\4EFB\52A1\6267\884C\8BB0\5F55\8868';
COMMENT ON TABLE jcgkzx_autotask.task_run_result IS U&'\4EFB\52A1\547D\4E2D\7ED3\679C\660E\7EC6\8868';
COMMENT ON TABLE jcgkzx_autotask.sms_send_log IS U&'\4EFB\52A1\77ED\4FE1\53D1\9001\8BB0\5F55\8868';
COMMENT ON TABLE jcgkzx_autotask.theme_source IS U&'\4E13\9898\76D1\6D4B\6570\636E\6E90\8868';
COMMENT ON TABLE jcgkzx_autotask.theme_topic IS U&'\4E13\9898\76D1\6D4B\4E3B\9898\8868';
COMMENT ON TABLE jcgkzx_autotask.theme_receiver_rule IS U&'\4E13\9898\63A5\6536\89C4\5219\8868';
COMMENT ON TABLE jcgkzx_autotask.theme_source_run IS U&'\4E13\9898\6570\636E\6E90\6267\884C\8BB0\5F55\8868';
COMMENT ON TABLE jcgkzx_autotask.theme_topic_result IS U&'\4E13\9898\547D\4E2D\7ED3\679C\660E\7EC6\8868';
COMMENT ON TABLE jcgkzx_autotask.theme_sms_send_log IS U&'\4E13\9898\77ED\4FE1\53D1\9001\8BB0\5F55\8868';
COMMENT ON TABLE jcgkzx_autotask.org_contact IS U&'\7EC4\7EC7\8054\7CFB\4EBA\4E3B\8868';
COMMENT ON TABLE jcgkzx_autotask.org_contact_phone IS U&'\8054\7CFB\4EBA\624B\673A\53F7\5B50\8868';
COMMENT ON TABLE jcgkzx_autotask.b_count IS U&'\8868\884C\6570\7EDF\8BA1\8868';

CREATE OR REPLACE FUNCTION jcgkzx_autotask.table_tj(schema_name TEXT)
RETURNS void
LANGUAGE plpgsql
AS $function$
DECLARE
    rec RECORD;
    total_count BIGINT;
BEGIN
    TRUNCATE TABLE jcgkzx_autotask.b_count;

    FOR rec IN
        SELECT
            t.table_name AS table_name,
            obj_description((schema_name || '.' || t.table_name)::regclass, 'pg_class') AS table_comment
        FROM information_schema.tables t
        WHERE t.table_schema = schema_name
          AND t.table_type = 'BASE TABLE'
          AND t.table_name <> 'b_count'
        ORDER BY t.table_name
    LOOP
        EXECUTE format('SELECT COUNT(*) FROM %I.%I', schema_name, rec.table_name) INTO total_count;

        INSERT INTO jcgkzx_autotask.b_count (bm, bzw, zs)
        VALUES (
            rec.table_name,
            COALESCE(rec.table_comment, ''),
            total_count::VARCHAR
        );
    END LOOP;

    INSERT INTO jcgkzx_autotask.b_count (bm, bzw, zs)
    SELECT
        'zzzz_hj',
        U&'\5408\8BA1',
        COALESCE(SUM(COALESCE(NULLIF(zs, ''), '0')::BIGINT), 0)::VARCHAR
    FROM jcgkzx_autotask.b_count;
END;
$function$;

SELECT jcgkzx_autotask.table_tj('jcgkzx_autotask');
