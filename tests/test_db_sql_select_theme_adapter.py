from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from types import SimpleNamespace
from zoneinfo import ZoneInfo

os.environ.setdefault("DATABASE_URL", "sqlite://")

from fastapi import HTTPException
from sqlalchemy import create_engine, text

from autotask_api.schemas import ThemeSourceCreate
from autotask_api.services.theme_adapters import get_theme_source_adapter
from autotask_api.services.theme_adapters.db_sql_select import DbSqlSelectThemeAdapter


class DbSqlSelectThemeAdapterTests(unittest.TestCase):
    def test_adapter_is_registered(self) -> None:
        adapter = get_theme_source_adapter("db_sql_select")
        self.assertIsInstance(adapter, DbSqlSelectThemeAdapter)

    def test_schema_accepts_db_sql_select_source_type(self) -> None:
        payload = ThemeSourceCreate(
            source_name="DB Source",
            source_code="db_source",
            source_type="db_sql_select",
            source_config={},
            schedule={
                "interval_value": 20,
                "interval_unit": "minute",
                "timezone": "Asia/Shanghai",
                "start_at": None,
                "end_at": None,
            },
        )
        self.assertEqual(payload.source_type, "db_sql_select")

    def test_fetch_normalizes_database_rows(self) -> None:
        adapter = DbSqlSelectThemeAdapter()
        source = SimpleNamespace(source_type="db_sql_select", source_code="db_source")
        now = datetime(2026, 4, 17, 12, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "source.db"
            sqlite_url = f"sqlite:///{db_path.as_posix()}"
            engine = create_engine(sqlite_url, future=True)
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        CREATE TABLE alerts (
                            id TEXT PRIMARY KEY,
                            case_no TEXT,
                            alarm_time TEXT,
                            dept_code TEXT,
                            dept_name TEXT,
                            content TEXT,
                            replies TEXT,
                            address TEXT
                        )
                        """
                    )
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO alerts (
                            id, case_no, alarm_time, dept_code, dept_name, content, replies, address
                        ) VALUES (
                            :id, :case_no, :alarm_time, :dept_code, :dept_name, :content, :replies, :address
                        )
                        """
                    ),
                    [
                        {
                            "id": "evt-001",
                            "case_no": "JQ-001",
                            "alarm_time": "2026-04-17 10:00:00",
                            "dept_code": "445302180000",
                            "dept_name": "Test Station",
                            "content": "violent conflict",
                            "replies": "handled",
                            "address": "Center Road",
                        },
                        {
                            "id": "evt-002",
                            "case_no": "JQ-002",
                            "alarm_time": "2026-04-17 11:30:00",
                            "dept_code": "445302190000",
                            "dept_name": "Second Station",
                            "content": "rental dispute",
                            "replies": "pending",
                            "address": "East Road",
                        },
                    ],
                )
            engine.dispose()

            os.environ["TEST_THEME_DB_URL"] = sqlite_url
            try:
                rows = adapter.fetch(
                    source=source,
                    source_config={
                        "credential_ref": {"url_env": "TEST_THEME_DB_URL"},
                        "query": (
                            "SELECT id, case_no, alarm_time, dept_code, dept_name, content, replies, address "
                            "FROM alerts "
                            "WHERE alarm_time >= :begin_time_text AND alarm_time < :end_time_text "
                            "ORDER BY alarm_time DESC"
                        ),
                        "time_range": {"mode": "rolling_hours", "hours_back": 3},
                        "fetch_profile": {"chunk_size": 1, "max_rows": 10},
                        "field_map": {
                            "event_key": "id",
                            "case_no": "case_no",
                            "alarmTime": "alarm_time",
                            "callTime": "alarm_time",
                            "sspcsdm": "dept_code",
                            "dutyDeptName": "dept_name",
                            "caseContents": "content",
                            "replies": "replies",
                            "occurAddress": "address",
                        },
                    },
                    now=now,
                    dry_run=True,
                )
            finally:
                os.environ.pop("TEST_THEME_DB_URL", None)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["event_key"], "evt-002")
        self.assertEqual(rows[0]["case_no"], "JQ-002")
        self.assertEqual(rows[0]["sspcsdm"], "445302190000")
        self.assertEqual(rows[0]["xqdm"], "445302")
        self.assertEqual(rows[0]["caseContents"], "rental dispute")
        self.assertEqual(rows[0]["replies"], "pending")
        self.assertEqual(rows[0]["occurAddress"], "East Road")
        self.assertEqual(rows[0]["message_vars"]["duty_dept_name"], "Second Station")
        self.assertEqual(rows[0]["raw_fields"]["id"], "evt-002")

    def test_fetch_rejects_non_read_only_query(self) -> None:
        adapter = DbSqlSelectThemeAdapter()
        source = SimpleNamespace(source_type="db_sql_select", source_code="db_source")
        with self.assertRaises(HTTPException) as ctx:
            adapter.fetch(
                source=source,
                source_config={
                    "database_url": "sqlite://",
                    "query": "DELETE FROM alerts",
                },
                now=datetime(2026, 4, 17, 12, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
                dry_run=True,
            )
        self.assertEqual(ctx.exception.status_code, 500)


if __name__ == "__main__":
    unittest.main()
