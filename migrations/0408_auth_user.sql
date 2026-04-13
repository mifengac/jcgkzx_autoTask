-- 0408_auth_user.sql
-- Target schema: jcgkzx_autotask
-- Adds the platform login user table and seeds the default admin account.

CREATE SCHEMA IF NOT EXISTS jcgkzx_autotask;

CREATE TABLE IF NOT EXISTS jcgkzx_autotask.platform_user (
    id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    is_builtin BOOLEAN NOT NULL DEFAULT FALSE,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_platform_user_username
    ON jcgkzx_autotask.platform_user (username);

INSERT INTO jcgkzx_autotask.platform_user (
    username,
    display_name,
    password_hash,
    enabled,
    is_builtin
)
SELECT
    'admin',
    '系统管理员',
    'pbkdf2_sha256$120000$autotask_admin_seed$07BeyVAy1VHkY7y3hw2LOC3aalGcocO9aczDHjcgHmo',
    TRUE,
    TRUE
WHERE NOT EXISTS (
    SELECT 1
    FROM jcgkzx_autotask.platform_user
    WHERE username = 'admin'
);
