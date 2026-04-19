from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "JCGKZX AutoTask API"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    auth_cookie_name: str = "autotask_session"
    auth_secret_key: str = "jcgkzx-autotask-auth-secret"
    auth_session_ttl_hours: int = 12

    database_url: str | None = None
    theme_db_url: str | None = Field(default=None, alias="THEME_DB_URL")
    db_schema: str = "jcgkzx_autotask"
    db_echo: bool = False
    auto_create_tables: bool = False

    upload_root: Path = Path("uploads")
    script_upload_dirname: str = "scripts"
    extract_root_dirname: str = "extracted"

    oracle_dsn: str | None = Field(default=None, alias="ORACLE_DSN")
    oracle_user: str | None = Field(default=None, alias="ORACLE_USER")
    oracle_password: str | None = Field(default=None, alias="ORACLE_PASSWORD")
    oracle_client_lib_dir: str | None = Field(default=None, alias="ORACLE_CLIENT_LIB_DIR")
    oracle_thick_mode: bool = Field(default=True, alias="ORACLE_THICK_MODE")

    sms_userid: str | None = Field(default=None, alias="SMS_USERID")
    sms_password: str | None = Field(default=None, alias="SMS_PASSWORD")
    sms_userport: str | None = Field(default=None, alias="SMS_USERPORT")
    sms_business_ports_json: str = Field(
        default='{"治安基础管控中心":"0006"}',
        alias="SMS_BUSINESS_PORTS_JSON",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @field_validator("database_url", "theme_db_url", mode="before")
    @classmethod
    def empty_string_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @property
    def sqlalchemy_database_uri(self) -> str:
        if self.database_url:
            return self.database_url
        raise RuntimeError("Missing database settings. Provide DATABASE_URL.")

    @property
    def script_upload_dir(self) -> Path:
        return self.upload_root / self.script_upload_dirname

    @property
    def script_extract_dir(self) -> Path:
        return self.upload_root / self.extract_root_dirname

    @property
    def sms_business_ports(self) -> dict[str, str]:
        try:
            parsed = json.loads(self.sms_business_ports_json)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return {str(key): str(value) for key, value in parsed.items()}
        return {}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
