from __future__ import annotations

from datetime import datetime
import os
import unittest

os.environ.setdefault("DATABASE_URL", "sqlite://")

from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from autotask_api.api.theme_runs import (
    get_theme_result,
    list_theme_results,
    list_theme_runs,
    list_theme_sms_logs,
)
from autotask_api.database import Base
from autotask_api.models import ThemeSmsSendLog, ThemeSource, ThemeSourceRun, ThemeTopic, ThemeTopicResult


def create_test_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def attach_schema(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("ATTACH DATABASE ':memory:' AS jcgkzx_autotask")
        cursor.close()

    return engine


class ThemeRunApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_test_engine()
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, future=True)
        self.seed_data()

    def tearDown(self) -> None:
        self.engine.dispose()

    def seed_data(self) -> None:
        with self.session_factory() as db:
            source_one = ThemeSource(
                source_name="Source Alpha",
                source_code="jingqing",
                source_type="dsjfx_case_list",
                enabled=True,
                interval_value=10,
                interval_unit="minute",
                timezone="Asia/Shanghai",
                source_config_json="{}",
            )
            source_two = ThemeSource(
                source_name="Source Beta",
                source_code="secondary",
                source_type="dsjfx_case_list",
                enabled=True,
                interval_value=20,
                interval_unit="minute",
                timezone="Asia/Shanghai",
                source_config_json="{}",
            )
            db.add_all([source_one, source_two])
            db.flush()

            topic_one = ThemeTopic(
                source_id=source_one.id,
                theme_name="Mental Alerts",
                theme_code="mental_case",
                enabled=True,
                priority=100,
                filter_expr_json="{}",
                dedup_mode="permanent",
                dedup_key_template="{event_key}",
            )
            topic_two = ThemeTopic(
                source_id=source_two.id,
                theme_name="Qingming Alerts",
                theme_code="qingming_case",
                enabled=True,
                priority=100,
                filter_expr_json="{}",
                dedup_mode="permanent",
                dedup_key_template="{event_key}",
            )
            db.add_all([topic_one, topic_two])
            db.flush()

            run_one = ThemeSourceRun(
                source_id=source_one.id,
                run_no="theme_1_run_1",
                status="completed",
                started_at=datetime(2026, 4, 5, 10, 0, 0),
                finished_at=datetime(2026, 4, 5, 10, 5, 0),
                fetched_count=10,
                matched_count=2,
                send_count=1,
                error_message="",
                log_path="",
            )
            run_two = ThemeSourceRun(
                source_id=source_two.id,
                run_no="theme_2_run_1",
                status="failed",
                started_at=datetime(2026, 4, 5, 11, 0, 0),
                finished_at=datetime(2026, 4, 5, 11, 4, 0),
                fetched_count=8,
                matched_count=1,
                send_count=0,
                error_message="oracle down",
                log_path="",
            )
            db.add_all([run_one, run_two])
            db.flush()

            result_one = ThemeTopicResult(
                source_run_id=run_one.id,
                topic_id=topic_one.id,
                event_key="evt-001",
                case_no="JQ-001",
                raw_result_json='{"caseContents":"mental alert case"}',
                rendered_message="Mental alert SMS",
                matched_rule_ids_json="[1]",
                receiver_mobiles_json='["13800000000"]',
                dedup_key="evt-001",
                oracle_eid="mental_case:evt-001",
                send_status="sent",
            )
            result_two = ThemeTopicResult(
                source_run_id=run_two.id,
                topic_id=topic_two.id,
                event_key="evt-002",
                case_no="JQ-002",
                raw_result_json='{"caseContents":"cemetery alert case"}',
                rendered_message="Qingming alert SMS",
                matched_rule_ids_json="[2]",
                receiver_mobiles_json='["13900000000"]',
                dedup_key="evt-002",
                oracle_eid="qingming_case:evt-002",
                send_status="failed",
            )
            db.add_all([result_one, result_two])
            db.flush()

            db.add_all([
                ThemeSmsSendLog(
                    source_run_id=run_one.id,
                    topic_result_id=result_one.id,
                    topic_id=topic_one.id,
                    mobile="13800000000",
                    content="Mental alert SMS",
                    provider="oracle_gateway",
                    provider_msg_id="MSG001",
                    status="sent",
                    error_message="",
                ),
                ThemeSmsSendLog(
                    source_run_id=run_two.id,
                    topic_result_id=result_two.id,
                    topic_id=topic_two.id,
                    mobile="13900000000",
                    content="Qingming alert SMS",
                    provider="oracle_gateway",
                    provider_msg_id="",
                    status="failed",
                    error_message="oracle down",
                ),
            ])
            db.commit()

    def test_list_theme_results_supports_filters_and_pagination(self) -> None:
        with self.session_factory() as db:
            payload = list_theme_results(
                source_id=1,
                topic_id=None,
                run_id=None,
                send_status="sent",
                keyword=None,
                start_time=None,
                end_time=None,
                limit=1,
                offset=0,
                db=db,
            )
        self.assertEqual(payload.total, 1)
        self.assertEqual(len(payload.items), 1)
        self.assertEqual(payload.items[0].topic_name, "Mental Alerts")

    def test_get_theme_result_returns_detail_payload(self) -> None:
        with self.session_factory() as db:
            payload = get_theme_result(1, db)
        self.assertEqual(payload.oracle_eid, "mental_case:evt-001")
        self.assertEqual(payload.raw_result["caseContents"], "mental alert case")

    def test_list_theme_sms_logs_supports_status_filter(self) -> None:
        with self.session_factory() as db:
            payload = list_theme_sms_logs(
                source_id=None,
                topic_id=None,
                run_id=None,
                status_text="failed",
                mobile=None,
                limit=20,
                offset=0,
                db=db,
            )
        self.assertEqual(payload.total, 1)
        self.assertEqual(payload.items[0].topic_code, "qingming_case")
        self.assertEqual(payload.items[0].status, "failed")

    def test_list_theme_runs_supports_topic_and_status_filters(self) -> None:
        with self.session_factory() as db:
            payload = list_theme_runs(
                source_id=None,
                topic_id=1,
                status_text="completed",
                limit=20,
                offset=0,
                db=db,
            )
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0].run_no, "theme_1_run_1")


if __name__ == "__main__":
    unittest.main()
