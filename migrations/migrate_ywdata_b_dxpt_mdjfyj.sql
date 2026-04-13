-- migrate_ywdata_b_dxpt_mdjfyj.sql
-- Full refresh migration from ywdata.b_dxpt_mdjfyj
-- Target tables:
--   jcgkzx_autotask.org_contact
--   jcgkzx_autotask.org_contact_phone
--
-- Behavior:
-- 1. Delete previously migrated rows whose source_system = 'ywdata.b_dxpt_mdjfyj'
-- 2. Re-insert contacts from ywdata.b_dxpt_mdjfyj
-- 3. Extract mobile numbers from lxdh and insert into org_contact_phone
--
-- Notes:
-- - This script only refreshes contacts imported from the legacy table.
-- - It does not touch manually maintained contacts from other source systems.
-- - Only mainland China mobile numbers matching 1[3-9][0-9]{9} are inserted into org_contact_phone.

BEGIN;

DELETE FROM jcgkzx_autotask.org_contact
WHERE source_system = 'ywdata.b_dxpt_mdjfyj';

WITH inserted_contacts AS (
    INSERT INTO jcgkzx_autotask.org_contact (
        source_system,
        source_pk,
        xq,
        xqdm,
        sspcs,
        sspcsdm,
        city_code,
        county_code,
        unit_level,
        xm,
        zw,
        rwzt,
        raw_lxdh,
        status,
        remark
    )
    SELECT
        'ywdata.b_dxpt_mdjfyj' AS source_system,
        CASE
            WHEN src.xh IS NULL THEN NULL
            ELSE src.xh::TEXT
        END AS source_pk,
        NULLIF(BTRIM(src.xq), '') AS xq,
        NULLIF(BTRIM(src.xqdm), '') AS xqdm,
        NULLIF(BTRIM(src.sspcs), '') AS sspcs,
        NULLIF(BTRIM(src.sspcsdm), '') AS sspcsdm,
        CASE
            WHEN BTRIM(src.sspcsdm) ~ '^\d{12}$' THEN SUBSTRING(BTRIM(src.sspcsdm) FROM 1 FOR 4) || '00000000'
            WHEN BTRIM(src.xqdm) ~ '^\d{6}$' THEN SUBSTRING(BTRIM(src.xqdm) FROM 1 FOR 4) || '00000000'
            ELSE NULL
        END AS city_code,
        CASE
            WHEN BTRIM(src.sspcsdm) ~ '^\d{12}$' THEN SUBSTRING(BTRIM(src.sspcsdm) FROM 1 FOR 6) || '000000'
            WHEN BTRIM(src.xqdm) ~ '^\d{6}$' THEN BTRIM(src.xqdm) || '000000'
            ELSE NULL
        END AS county_code,
        CASE
            WHEN BTRIM(src.sspcsdm) ~ '^\d{4}00000000$' THEN 'city'
            WHEN BTRIM(src.sspcsdm) ~ '^\d{6}000000$' THEN 'county'
            WHEN BTRIM(src.sspcsdm) ~ '^\d{12}$' THEN 'station'
            ELSE 'unknown'
        END AS unit_level,
        NULLIF(BTRIM(src.xm), '') AS xm,
        NULLIF(BTRIM(src.zw), '') AS zw,
        NULLIF(BTRIM(src.rwzt), '') AS rwzt,
        NULLIF(BTRIM(src.lxdh), '') AS raw_lxdh,
        'active' AS status,
        COALESCE(NULLIF(BTRIM(src.bz), ''), '__EMPTY_TEXT__') AS remark
    FROM ywdata.b_dxpt_mdjfyj AS src
    RETURNING id, raw_lxdh
),
matched_phones AS (
    SELECT
        ic.id AS contact_id,
        match_item[1] AS phone_raw,
        match_item[1] AS mobile,
        ROW_NUMBER() OVER (PARTITION BY ic.id ORDER BY match_item[1]) AS rn
    FROM inserted_contacts AS ic
    CROSS JOIN LATERAL REGEXP_MATCHES(
        COALESCE(ic.raw_lxdh, ''),
        '(1[3-9][0-9]{9})',
        'g'
    ) AS match_item
)
INSERT INTO jcgkzx_autotask.org_contact_phone (
    contact_id,
    phone_raw,
    mobile,
    is_primary,
    status
)
SELECT
    mp.contact_id,
    mp.phone_raw,
    mp.mobile,
    CASE
        WHEN mp.rn = 1 THEN TRUE
        ELSE FALSE
    END AS is_primary,
    'active' AS status
FROM matched_phones AS mp;

COMMIT;
