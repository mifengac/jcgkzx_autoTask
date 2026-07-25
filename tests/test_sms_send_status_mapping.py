from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SMS_GATEWAY_BASE_URL", "http://sms-gateway.test:5011")
os.environ.setdefault("SMS_GATEWAY_TOKEN", "test-token")
os.environ.setdefault("SMS_GATEWAY_MAX_RETRIES", "0")

from fastapi import HTTPException
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from autotask_api.database import Base
from autotask_api.models import (
    AlertTask,
    ScriptDefinition,
    ScriptVersion,
    SmsSendLog,
    TaskRule,
    TaskRunResult,
    ThemeReceiverRule,
    ThemeSmsSendLog,
    ThemeSource,
    ThemeTopic,
    ThemeTopicResult,
)
from autotask_api.schemas import TaskRunRequest, ThemeSourceRunRequest
from autotask_api.services.sms_gateway_client import SmsSendOutcome
from autotask_api.services.task_executor import execute_task_run
from autotask_api.services.theme_executor import execute_theme_source_run


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


class TaskSmsStatusMappingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_test_engine()
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, future=True)
        self.task_id = self._seed_task()

    def tearDown(self) -> None:
        self.engine.dispose()

    def _seed_task(self) -> int:
        with self.session_factory() as db:
            script = ScriptDefinition(
                script_name="s",
                script_code="s_sms_map",
                entry_file="main.py",
                entry_func="run",
                status="active",
            )
            db.add(script)
            db.flush()
            version = ScriptVersion(
                script_id=script.id,
                version_no="1",
                package_path="/tmp/x.zip",
                checksum="abc",
            )
            db.add(version)
            db.flush()
            task = AlertTask(
                task_name="sms map task",
                script_id=script.id,
                script_version_id=version.id,
                enabled=True,
                runtime_config_json="{}",
            )
            db.add(task)
            db.flush()
            rule = TaskRule(
                task_id=task.id,
                rule_name="fixed",
                rule_type="fixed_receivers",
                priority=1,
                enabled=True,
                fixed_receivers_json='["13800138001","13800138002"]',
            )
            db.add(rule)
            db.commit()
            return task.id

    def _run_with_outcomes(self, outcomes: list[SmsSendOutcome]) -> tuple[list[SmsSendLog], TaskRunResult]:
        outcome_iter = iter(outcomes)

        def fake_send_one(**_kwargs):
            return next(outcome_iter)

        with self.session_factory() as db:
            with (
                patch(
                    "autotask_api.services.task_executor.execute_script",
                    return_value=[{"event_id": "E-TASK-1", "message_text": "hello"}],
                ),
                patch(
                    "autotask_api.services.task_executor.SmsGatewayClient"
                ) as mock_cls,
            ):
                client = MagicMock()
                client.provider_name = "oracle_sms_gateway"
                client.resolve_biz.return_value = "yfjcgkzx"
                client.send_one.side_effect = fake_send_one
                mock_cls.return_value = client
                mock_cls.provider_name = "oracle_sms_gateway"

                execute_task_run(db, self.task_id, TaskRunRequest(dry_run=False))

            logs = list(db.scalars(select(SmsSendLog).order_by(SmsSendLog.id)).all())
            result = db.scalar(select(TaskRunResult).order_by(TaskRunResult.id.desc()))
            assert result is not None
            return logs, result

    def test_three_outcomes_persist_to_sms_log(self) -> None:
        # Two mobiles on the rule; exercise mixed statuses across two runs.
        logs, result = self._run_with_outcomes(
            [
                SmsSendOutcome(status="sent"),
                SmsSendOutcome(status="failed", error_message="blocked"),
            ]
        )
        self.assertEqual([log.status for log in logs], ["sent", "failed"])
        self.assertEqual(logs[1].error_message, "blocked")
        self.assertEqual(result.send_status, "partial_failed")

    def test_all_skipped_duplicate(self) -> None:
        logs, result = self._run_with_outcomes(
            [
                SmsSendOutcome(status="skipped_duplicate"),
                SmsSendOutcome(status="skipped_duplicate"),
            ]
        )
        self.assertEqual([log.status for log in logs], ["skipped_duplicate", "skipped_duplicate"])
        self.assertEqual(result.send_status, "skipped_duplicate")

    def test_all_sent(self) -> None:
        _logs, result = self._run_with_outcomes(
            [SmsSendOutcome(status="sent"), SmsSendOutcome(status="sent")]
        )
        self.assertEqual(result.send_status, "sent")

    def test_all_failed(self) -> None:
        logs, result = self._run_with_outcomes(
            [
                SmsSendOutcome(status="failed", error_message="x"),
                SmsSendOutcome(status="failed", error_message="y"),
            ]
        )
        self.assertEqual(result.send_status, "failed")
        self.assertEqual(logs[0].error_message, "x")

    def test_http_exception_logs_failed_and_continues(self) -> None:
        call_count = {"n": 0}

        def fake_send_one(**_kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise HTTPException(status_code=502, detail="SMS gateway unavailable (HTTP 503)")
            return SmsSendOutcome(status="sent")

        with self.session_factory() as db:
            with (
                patch(
                    "autotask_api.services.task_executor.execute_script",
                    return_value=[{"event_id": "E-TASK-2", "message_text": "hello"}],
                ),
                patch(
                    "autotask_api.services.task_executor.SmsGatewayClient"
                ) as mock_cls,
            ):
                client = MagicMock()
                client.provider_name = "oracle_sms_gateway"
                client.resolve_biz.return_value = "yfjcgkzx"
                client.send_one.side_effect = fake_send_one
                mock_cls.return_value = client
                mock_cls.provider_name = "oracle_sms_gateway"

                run = execute_task_run(db, self.task_id, TaskRunRequest(dry_run=False))
                self.assertEqual(run.status, "completed")

            logs = list(db.scalars(select(SmsSendLog).order_by(SmsSendLog.id)).all())
            result = db.scalar(select(TaskRunResult).order_by(TaskRunResult.id.desc()))
            assert result is not None
            self.assertEqual([log.status for log in logs], ["failed", "sent"])
            self.assertIn("503", logs[0].error_message)
            self.assertEqual(result.send_status, "partial_failed")


class ThemeSmsStatusMappingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_test_engine()
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, future=True)
        self.source_id = self._seed_source()

    def tearDown(self) -> None:
        self.engine.dispose()

    def _seed_source(self) -> int:
        with self.session_factory() as db:
            source = ThemeSource(
                source_name="src",
                source_code="src_sms_map",
                source_type="dsjfx_case_list",
                enabled=True,
                interval_value=10,
                interval_unit="minute",
                source_config_json="{}",
            )
            db.add(source)
            db.flush()
            topic = ThemeTopic(
                source_id=source.id,
                theme_name="topic",
                theme_code="topic_sms_map",
                enabled=True,
                priority=1,
                filter_expr_json="{}",
                dedup_mode="window",
                dedup_window_minutes=30,
                dedup_key_template="{event_key}",
            )
            db.add(topic)
            db.flush()
            rule = ThemeReceiverRule(
                topic_id=topic.id,
                rule_name="fixed",
                rule_type="fixed_receivers",
                priority=1,
                enabled=True,
                fixed_receivers_json='["13800138001","13800138002"]',
            )
            db.add(rule)
            db.commit()
            return source.id

    def _run_with_outcomes(
        self, outcomes: list[SmsSendOutcome] | list[Exception]
    ) -> tuple[list[ThemeSmsSendLog], ThemeTopicResult]:
        outcome_iter = iter(outcomes)

        def fake_send_one(**_kwargs):
            item = next(outcome_iter)
            if isinstance(item, Exception):
                raise item
            return item

        rows = [{"event_key": "E-THEME-1", "message_text": "theme hello"}]
        adapter = MagicMock()
        adapter.fetch.return_value = rows

        with self.session_factory() as db:
            with (
                patch(
                    "autotask_api.services.theme_executor.get_theme_source_adapter",
                    return_value=adapter,
                ),
                patch(
                    "autotask_api.services.theme_executor.SmsGatewayClient"
                ) as mock_cls,
            ):
                client = MagicMock()
                client.provider_name = "oracle_sms_gateway"
                client.resolve_biz.return_value = "yfjcgkzx"
                client.send_one.side_effect = fake_send_one
                mock_cls.return_value = client
                mock_cls.provider_name = "oracle_sms_gateway"

                execute_theme_source_run(
                    db, self.source_id, ThemeSourceRunRequest(dry_run=False)
                )

            logs = list(
                db.scalars(select(ThemeSmsSendLog).order_by(ThemeSmsSendLog.id)).all()
            )
            result = db.scalar(
                select(ThemeTopicResult).order_by(ThemeTopicResult.id.desc())
            )
            assert result is not None
            return logs, result

    def test_theme_mixed_partial_failed(self) -> None:
        logs, result = self._run_with_outcomes(
            [
                SmsSendOutcome(status="sent"),
                SmsSendOutcome(status="failed", error_message="bad"),
            ]
        )
        self.assertEqual([log.status for log in logs], ["sent", "failed"])
        self.assertEqual(logs[1].error_message, "bad")
        self.assertEqual(result.send_status, "partial_failed")

    def test_theme_all_skipped(self) -> None:
        logs, result = self._run_with_outcomes(
            [
                SmsSendOutcome(status="skipped_duplicate"),
                SmsSendOutcome(status="skipped_duplicate"),
            ]
        )
        self.assertEqual(result.send_status, "skipped_duplicate")
        self.assertEqual(logs[0].status, "skipped_duplicate")

    def test_theme_http_exception_does_not_abort_run(self) -> None:
        logs, result = self._run_with_outcomes(
            [
                HTTPException(status_code=502, detail="Failed to reach SMS gateway"),
                SmsSendOutcome(status="sent"),
            ]
        )
        self.assertEqual([log.status for log in logs], ["failed", "sent"])
        self.assertEqual(result.send_status, "partial_failed")


if __name__ == "__main__":
    unittest.main()
