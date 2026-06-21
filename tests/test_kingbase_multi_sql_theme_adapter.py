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
from autotask_api.services.theme_adapters.kingbase_multi_sql import KingbaseMultiSqlThemeAdapter


class KingbaseMultiSqlThemeAdapterTests(unittest.TestCase):
    def test_adapter_is_registered(self) -> None:
        adapter = get_theme_source_adapter("kingbase_multi_sql")
        self.assertIsInstance(adapter, KingbaseMultiSqlThemeAdapter)

    def test_schema_accepts_kingbase_multi_sql_source_type(self) -> None:
        payload = ThemeSourceCreate(
            source_name="Kingbase Multi SQL",
            source_code="dxpt_multi",
            source_type="kingbase_multi_sql",
            source_config={},
            schedule={
                "interval_value": 20,
                "interval_unit": "minute",
                "timezone": "Asia/Shanghai",
                "start_at": None,
                "end_at": None,
            },
        )
        self.assertEqual(payload.source_type, "kingbase_multi_sql")

    def test_fetch_executes_multiple_queries_and_tags_rows(self) -> None:
        adapter = KingbaseMultiSqlThemeAdapter()
        source = SimpleNamespace(source_type="kingbase_multi_sql", source_code="dxpt_multi")
        now = datetime(2026, 4, 19, 12, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "source.db"
            sqlite_url = f"sqlite:///{db_path.as_posix()}"
            engine = create_engine(sqlite_url, future=True)
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        CREATE TABLE disputes (
                            id TEXT PRIMARY KEY,
                            business_no TEXT,
                            station_code TEXT,
                            content TEXT,
                            transfer_status_code TEXT
                        )
                        """
                    )
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO disputes (
                            id, business_no, station_code, content, transfer_status_code
                        ) VALUES (
                            :id, :business_no, :station_code, :content, :transfer_status_code
                        )
                        """
                    ),
                    [
                        {
                            "id": "evt-001",
                            "business_no": "YW001",
                            "station_code": "445302190000",
                            "content": "24h pending",
                            "transfer_status_code": "u24",
                        },
                        {
                            "id": "evt-002",
                            "business_no": "YW002",
                            "station_code": "445302180000",
                            "content": "36h pending",
                            "transfer_status_code": "u36",
                        },
                    ],
                )
            engine.dispose()

            original_theme_db_url = os.environ.get("THEME_DB_URL")
            os.environ["THEME_DB_URL"] = sqlite_url
            try:
                rows = adapter.fetch(
                    source=source,
                    source_config={
                        "fetch_profile": {"chunk_size": 1, "max_rows": 10},
                        "field_map": {
                            "event_key": "id",
                            "case_no": "business_no",
                            "sspcsdm": "station_code",
                            "caseContents": "content",
                        },
                        "queries": [
                            {
                                "query_code": "dxpt_u24",
                                "topic_codes": ["dxpt_u24"],
                                "query": (
                                    "SELECT id, business_no, station_code, content, transfer_status_code "
                                    "FROM disputes WHERE transfer_status_code = :status"
                                ),
                                "query_params": {"status": "u24"},
                            },
                            {
                                "query_code": "dxpt_u36",
                                "topic_codes": ["dxpt_u36"],
                                "query": (
                                    "SELECT id, business_no, station_code, content, transfer_status_code "
                                    "FROM disputes WHERE transfer_status_code = :status"
                                ),
                                "query_params": {"status": "u36"},
                            },
                        ],
                    },
                    now=now,
                    dry_run=True,
                )
            finally:
                if original_theme_db_url is None:
                    os.environ.pop("THEME_DB_URL", None)
                else:
                    os.environ["THEME_DB_URL"] = original_theme_db_url

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["event_key"], "evt-001")
        self.assertEqual(rows[0]["case_no"], "YW001")
        self.assertEqual(rows[0]["sspcsdm"], "445302190000")
        self.assertEqual(rows[0]["source_query_code"], "dxpt_u24")
        self.assertEqual(rows[0]["source_query_index"], 1)
        self.assertEqual(rows[0]["target_topic_codes"], ["dxpt_u24"])
        self.assertEqual(rows[0]["message_vars"]["source_query_code"], "dxpt_u24")
        self.assertEqual(rows[1]["event_key"], "evt-002")
        self.assertEqual(rows[1]["source_query_code"], "dxpt_u36")
        self.assertEqual(rows[1]["target_topic_codes"], ["dxpt_u36"])

    def test_theme_db_url_takes_priority_over_database_url(self) -> None:
        adapter = KingbaseMultiSqlThemeAdapter()
        source = SimpleNamespace(source_type="kingbase_multi_sql", source_code="dxpt_multi")
        now = datetime(2026, 4, 19, 12, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

        with TemporaryDirectory() as tmpdir:
            good_db_path = Path(tmpdir) / "theme.db"
            bad_db_path = Path(tmpdir) / "platform.db"
            theme_url = f"sqlite:///{good_db_path.as_posix()}"
            platform_url = f"sqlite:///{bad_db_path.as_posix()}"
            engine = create_engine(theme_url, future=True)
            with engine.begin() as connection:
                connection.execute(text("CREATE TABLE disputes (id TEXT PRIMARY KEY)"))
                connection.execute(text("INSERT INTO disputes (id) VALUES ('theme-db-row')"))
            engine.dispose()

            original_theme_db_url = os.environ.get("THEME_DB_URL")
            original_database_url = os.environ.get("DATABASE_URL")
            os.environ["THEME_DB_URL"] = theme_url
            os.environ["DATABASE_URL"] = platform_url
            try:
                rows = adapter.fetch(
                    source=source,
                    source_config={
                        "queries": [
                            {
                                "query_code": "priority",
                                "topic_codes": ["dxpt_priority"],
                                "query": "SELECT id FROM disputes",
                            }
                        ]
                    },
                    now=now,
                    dry_run=True,
                )
            finally:
                if original_theme_db_url is None:
                    os.environ.pop("THEME_DB_URL", None)
                else:
                    os.environ["THEME_DB_URL"] = original_theme_db_url
                if original_database_url is None:
                    os.environ.pop("DATABASE_URL", None)
                else:
                    os.environ["DATABASE_URL"] = original_database_url

        self.assertEqual(rows[0]["event_key"], "theme-db-row")

    def test_fetch_rejects_non_read_only_query(self) -> None:
        adapter = KingbaseMultiSqlThemeAdapter()
        source = SimpleNamespace(source_type="kingbase_multi_sql", source_code="dxpt_multi")
        original_theme_db_url = os.environ.get("THEME_DB_URL")
        os.environ["THEME_DB_URL"] = "sqlite://"
        try:
            with self.assertRaises(HTTPException) as ctx:
                adapter.fetch(
                    source=source,
                    source_config={
                        "queries": [
                            {
                                "query_code": "bad",
                                "topic_codes": ["dxpt_bad"],
                                "query": "DELETE FROM disputes",
                            }
                        ],
                    },
                    now=datetime(2026, 4, 19, 12, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
                    dry_run=True,
                )
        finally:
            if original_theme_db_url is None:
                os.environ.pop("THEME_DB_URL", None)
            else:
                os.environ["THEME_DB_URL"] = original_theme_db_url
        self.assertEqual(ctx.exception.status_code, 500)

    def test_fetch_fails_when_any_query_fails(self) -> None:
        adapter = KingbaseMultiSqlThemeAdapter()
        source = SimpleNamespace(source_type="kingbase_multi_sql", source_code="dxpt_multi")
        original_theme_db_url = os.environ.get("THEME_DB_URL")
        os.environ["THEME_DB_URL"] = "sqlite://"
        try:
            with self.assertRaises(HTTPException) as ctx:
                adapter.fetch(
                    source=source,
                    source_config={
                        "queries": [
                            {
                                "query_code": "first",
                                "topic_codes": ["dxpt_first"],
                                "query": "SELECT 1 AS id",
                            },
                            {
                                "query_code": "missing",
                                "topic_codes": ["dxpt_missing"],
                                "query": "SELECT * FROM missing_table",
                            },
                        ],
                    },
                    now=datetime(2026, 4, 19, 12, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
                    dry_run=True,
                )
        finally:
            if original_theme_db_url is None:
                os.environ.pop("THEME_DB_URL", None)
            else:
                os.environ["THEME_DB_URL"] = original_theme_db_url
        self.assertEqual(ctx.exception.status_code, 502)


if __name__ == "__main__":
    unittest.main()
