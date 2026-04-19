-- 0417_theme_source_db_sql_select.sql
-- Allow theme_source.source_type to use database-backed SQL data sources.

ALTER TABLE jcgkzx_autotask.theme_source
    DROP CONSTRAINT IF EXISTS ck_theme_source_type;

ALTER TABLE jcgkzx_autotask.theme_source
    ADD CONSTRAINT ck_theme_source_type
    CHECK (source_type IN ('dsjfx_case_list', 'db_sql_select'));
