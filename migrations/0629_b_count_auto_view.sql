-- 0629_b_count_auto_view.sql
-- 将 b_count 由「物理表 + table_tj 手动刷新」改为「实时视图」，查询即最新行数，无需任何调度。
-- 适用于自建的 jcgkzx_autotask 与 jcgkzx_monitor 两个 schema。
-- 说明：本实例 job_queue_processes=0，数据库侧定时作业不可用；视图方案纯 DB 侧、零维护。

-- ============================ jcgkzx_autotask ============================
-- 集返回函数：动态统计指定 schema 下每张基表的行数，并在末尾追加「合计」行
CREATE OR REPLACE FUNCTION jcgkzx_autotask.b_count_tj(schema_name TEXT)
RETURNS TABLE(bm VARCHAR, bzw VARCHAR, zs VARCHAR, gxsj TIMESTAMP)
LANGUAGE plpgsql
STABLE
AS $function$
DECLARE
    rec     RECORD;
    cnt     BIGINT;
    total   BIGINT := 0;
    ts      TIMESTAMP := now();
BEGIN
    FOR rec IN
        SELECT
            t.table_name AS tn,
            obj_description((quote_ident(schema_name) || '.' || quote_ident(t.table_name))::regclass, 'pg_class') AS tc
        FROM information_schema.tables t
        WHERE t.table_schema = schema_name
          AND t.table_type = 'BASE TABLE'
          AND t.table_name <> 'b_count'
        ORDER BY t.table_name
    LOOP
        EXECUTE format('SELECT COUNT(*) FROM %I.%I', schema_name, rec.tn) INTO cnt;
        total := total + cnt;
        bm := rec.tn;
        bzw := COALESCE(rec.tc, '');
        zs := cnt::VARCHAR;
        gxsj := ts;
        RETURN NEXT;
    END LOOP;

    bm := 'zzzz_hj';
    bzw := '合计';
    zs := total::VARCHAR;
    gxsj := ts;
    RETURN NEXT;
END;
$function$;
COMMENT ON FUNCTION jcgkzx_autotask.b_count_tj(TEXT) IS '动态统计指定 schema 各基表行数（含合计），供 b_count 视图调用';

-- 旧的物理表不再需要：删除后以同名视图替代
DROP TABLE IF EXISTS jcgkzx_autotask.b_count;
CREATE VIEW jcgkzx_autotask.b_count AS
    SELECT bm, bzw, zs, gxsj FROM jcgkzx_autotask.b_count_tj('jcgkzx_autotask');
COMMENT ON VIEW jcgkzx_autotask.b_count IS '表行数统计（实时视图，查询即最新）';

-- 旧的手动刷新函数已被视图取代，改为无操作提示，避免历史调用方报错
CREATE OR REPLACE FUNCTION jcgkzx_autotask.table_tj(schema_name TEXT)
RETURNS void
LANGUAGE plpgsql
AS $function$
BEGIN
    RAISE NOTICE 'b_count 现为实时视图，无需刷新（schema=%）', schema_name;
END;
$function$;
COMMENT ON FUNCTION jcgkzx_autotask.table_tj(TEXT) IS '已废弃：b_count 改为实时视图后无需手动刷新，保留为兼容占位';

-- ============================ jcgkzx_monitor ============================
CREATE OR REPLACE FUNCTION jcgkzx_monitor.b_count_tj(schema_name TEXT)
RETURNS TABLE(bm VARCHAR, bzw VARCHAR, zs VARCHAR, gxsj TIMESTAMP)
LANGUAGE plpgsql
STABLE
AS $function$
DECLARE
    rec     RECORD;
    cnt     BIGINT;
    total   BIGINT := 0;
    ts      TIMESTAMP := now();
BEGIN
    FOR rec IN
        SELECT
            t.table_name AS tn,
            obj_description((quote_ident(schema_name) || '.' || quote_ident(t.table_name))::regclass, 'pg_class') AS tc
        FROM information_schema.tables t
        WHERE t.table_schema = schema_name
          AND t.table_type = 'BASE TABLE'
          AND t.table_name <> 'b_count'
        ORDER BY t.table_name
    LOOP
        EXECUTE format('SELECT COUNT(*) FROM %I.%I', schema_name, rec.tn) INTO cnt;
        total := total + cnt;
        bm := rec.tn;
        bzw := COALESCE(rec.tc, '');
        zs := cnt::VARCHAR;
        gxsj := ts;
        RETURN NEXT;
    END LOOP;

    bm := 'zzzz_hj';
    bzw := '合计';
    zs := total::VARCHAR;
    gxsj := ts;
    RETURN NEXT;
END;
$function$;
COMMENT ON FUNCTION jcgkzx_monitor.b_count_tj(TEXT) IS '动态统计指定 schema 各基表行数（含合计），供 b_count 视图调用';

DROP TABLE IF EXISTS jcgkzx_monitor.b_count;
CREATE VIEW jcgkzx_monitor.b_count AS
    SELECT bm, bzw, zs, gxsj FROM jcgkzx_monitor.b_count_tj('jcgkzx_monitor');
COMMENT ON VIEW jcgkzx_monitor.b_count IS '表行数统计（实时视图，查询即最新）';

CREATE OR REPLACE FUNCTION jcgkzx_monitor.table_tj(schema_name TEXT)
RETURNS void
LANGUAGE plpgsql
AS $function$
BEGIN
    RAISE NOTICE 'b_count 现为实时视图，无需刷新（schema=%）', schema_name;
END;
$function$;
COMMENT ON FUNCTION jcgkzx_monitor.table_tj(TEXT) IS '已废弃：b_count 改为实时视图后无需手动刷新，保留为兼容占位';
