from __future__ import annotations

from collections.abc import Generator
import re

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql.base import PGDialect
from sqlalchemy.dialects.postgresql.psycopg2 import PGDialect_psycopg2
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from autotask_api.config import get_settings


settings = get_settings()


class Base(DeclarativeBase):
    pass


def _kingbase_compatible_server_version_info(self, connection):
    version_text = connection.exec_driver_sql("select pg_catalog.version()").scalar()
    patterns = (
        r".*(?:PostgreSQL|EnterpriseDB) "
        r"(\d+)\.?(\d+)?(?:\.(\d+))?(?:\.\d+)?(?:devel|beta)?",
        r".*KingbaseES\s+V(\d+)R(\d+)C(\d+)(?:B(\d+))?.*",
    )
    for pattern in patterns:
        match = re.match(pattern, version_text, re.IGNORECASE)
        if match:
            return tuple(int(part) for part in match.groups()[:3] if part is not None)
    raise AssertionError(f"Could not determine version from string '{version_text}'")


PGDialect._get_server_version_info = _kingbase_compatible_server_version_info
PGDialect_psycopg2._get_server_version_info = _kingbase_compatible_server_version_info


engine = create_engine(
    settings.sqlalchemy_database_uri,
    echo=settings.db_echo,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    if settings.auto_create_tables:
        Base.metadata.create_all(bind=engine)
