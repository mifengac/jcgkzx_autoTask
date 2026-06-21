-- 0419_theme_source_kingbase_multi_sql.sql
-- Allow theme_source.source_type to use one Kingbase-compatible connection with multiple SQL queries.

ALTER TABLE jcgkzx_autotask.theme_source
    DROP CONSTRAINT IF EXISTS ck_theme_source_type;

ALTER TABLE jcgkzx_autotask.theme_source
    ADD CONSTRAINT ck_theme_source_type
    CHECK (source_type IN ('dsjfx_case_list', 'db_sql_select', 'kingbase_multi_sql'));
