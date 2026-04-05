-- 0309dev_migrate_contacts.sql
-- Migrate legacy contact data from ywdata.b_dxpt_mdjfyj to jcgkzx_autotask.
-- Run after 0309dev_schema.sql in a writable client.

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
            WHEN xh IS NULL THEN NULL
            ELSE xh::TEXT
        END AS source_pk,
        NULLIF(BTRIM(xq), '') AS xq,
        NULLIF(BTRIM(xqdm), '') AS xqdm,
        NULLIF(BTRIM(sspcs), '') AS sspcs,
        NULLIF(BTRIM(sspcsdm), '') AS sspcsdm,
        CASE
            WHEN BTRIM(sspcsdm) ~ '^\d{12}$' THEN SUBSTRING(BTRIM(sspcsdm) FROM 1 FOR 4) || '00000000'
            WHEN BTRIM(xqdm) ~ '^\d{6}$' THEN SUBSTRING(BTRIM(xqdm) FROM 1 FOR 4) || '00000000'
            ELSE NULL
        END AS city_code,
        CASE
            WHEN BTRIM(sspcsdm) ~ '^\d{12}$' THEN SUBSTRING(BTRIM(sspcsdm) FROM 1 FOR 6) || '000000'
            WHEN BTRIM(xqdm) ~ '^\d{6}$' THEN BTRIM(xqdm) || '000000'
            ELSE NULL
        END AS county_code,
        CASE
            WHEN BTRIM(sspcsdm) ~ '^\d{4}00000000$' THEN 'city'
            WHEN BTRIM(sspcsdm) ~ '^\d{6}000000$' THEN 'county'
            WHEN BTRIM(sspcsdm) ~ '^\d{12}$' THEN 'station'
            ELSE 'unknown'
        END AS unit_level,
        NULLIF(BTRIM(xm), '') AS xm,
        NULLIF(BTRIM(zw), '') AS zw,
        NULLIF(BTRIM(rwzt), '') AS rwzt,
        NULLIF(BTRIM(lxdh), '') AS raw_lxdh,
        'active' AS status,
        COALESCE(NULLIF(BTRIM(bz), ''), '__EMPTY_TEXT__') AS remark
    FROM ywdata.b_dxpt_mdjfyj
    RETURNING id, raw_lxdh
),
matched_phones AS (
    SELECT
        ic.id AS contact_id,
        match_item[1] AS phone_raw,
        match_item[1] AS mobile,
        ROW_NUMBER() OVER (PARTITION BY ic.id ORDER BY match_item[1]) AS rn
    FROM inserted_contacts ic
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
    contact_id,
    phone_raw,
    mobile,
    CASE
        WHEN rn = 1 THEN TRUE
        ELSE FALSE
    END AS is_primary,
    'active' AS status
FROM matched_phones
ON CONFLICT (contact_id, mobile) DO NOTHING;
