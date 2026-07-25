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

    # Deprecated for platform SMS send: credentials live on oracle-sms-gateway.
    sms_userid: str | None = Field(default=None, alias="SMS_USERID")
    sms_password: str | None = Field(default=None, alias="SMS_PASSWORD")
    sms_userport: str | None = Field(default=None, alias="SMS_USERPORT")
    sms_business_ports_json: str = Field(
        default='{"治安基础管控中心":"0006"}',
        alias="SMS_BUSINESS_PORTS_JSON",
    )

    # HTTP SMS gateway (oracle-sms-gateway)
    sms_gateway_base_url: str = Field(
        default="http://127.0.0.1:5011",
        alias="SMS_GATEWAY_BASE_URL",
    )
    sms_gateway_token: str | None = Field(default=None, alias="SMS_GATEWAY_TOKEN")
    sms_gateway_biz: str = Field(default="yfjcgkzx", alias="SMS_GATEWAY_BIZ")
    sms_gateway_timeout_seconds: float = Field(
        default=10.0,
        alias="SMS_GATEWAY_TIMEOUT_SECONDS",
    )
    # Extra attempts after the first try on ConnectionError/Timeout/5xx (not 4xx).
    sms_gateway_max_retries: int = Field(default=2, alias="SMS_GATEWAY_MAX_RETRIES")
    # Approximation of former permanent dedup (no since window) via a large hour window.
    # Sent to the gateway as minutes: permanent_dedup_hours * 60.
    sms_gateway_permanent_dedup_hours: int = Field(
        default=87600,
        alias="SMS_GATEWAY_PERMANENT_DEDUP_HOURS",
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
