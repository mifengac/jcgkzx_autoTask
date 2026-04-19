from __future__ import annotations

from datetime import datetime
import os
from types import SimpleNamespace
import unittest
from zoneinfo import ZoneInfo

os.environ.setdefault("DATABASE_URL", "sqlite://")

from autotask_api.services.theme_adapters.dsjfx_case_list import DsjfxCaseListThemeAdapter
from autotask_api.services.theme_executor import (
    build_theme_dedup_key,
    build_theme_message,
    build_theme_oracle_eid,
    theme_dedup_since,
    topic_allows_row,
)


class ThemeAdapterAndExecutorTests(unittest.TestCase):
    def test_adapter_normalizes_row(self) -> None:
        adapter = DsjfxCaseListThemeAdapter()
        row = adapter._normalize_row(
            {
                "caseNo": "JQ-001",
                "callTime": "2026-04-04 09:00:00",
                "alarmTime": "2026-04-04 10:00:00",
                "dutyDeptNo": "445302180000",
                "dutyDeptName": "Test Police Station",
                "caseContents": "minor incident",
                "replies": "already handled",
            },
            "dsjfx_case_main",
            1,
        )
        self.assertEqual(row["event_key"], "JQ-001")
        self.assertEqual(row["case_no"], "JQ-001")
        self.assertEqual(row["sspcsdm"], "445302180000")
        self.assertEqual(row["xqdm"], "445302")
        self.assertEqual(row["message_vars"]["duty_dept_name"], "Test Police Station")
        self.assertEqual(row["message_vars"]["alarmTime"], "2026-04-04 10:00:00")
        self.assertEqual(row["message_vars"]["callTime"], "2026-04-04 09:00:00")

    def test_build_theme_message_includes_alarm_time(self) -> None:
        topic = SimpleNamespace(
            filter_expr_json='{"field":"caseContents","op":"contains_any","value":["foo","bar"]}',
            message_template=SimpleNamespace(
                template_content="Time:{alarmTime}\nPlace:{occur_address}"
            ),
        )
        row = {
            "caseContents": "foo incident",
            "alarmTime": "2026-04-04 10:00:00",
            "occur_address": "Center",
            "message_vars": {"case_no": "JQ-002", "callTime": "2026-04-04 09:00:00"},
        }
        message = build_theme_message(topic, row)
        self.assertEqual(message, "Time:2026-04-04 10:00:00\nPlace:Center")

    def test_build_theme_dedup_key_and_eid(self) -> None:
        topic = SimpleNamespace(
            dedup_key_template="{case_no}",
            theme_code="juvenile_case",
            filter_expr_json='{"field":"caseContents","op":"contains_any","value":["foo","bar"]}',
        )
        row = {
            "case_no": "JQ-002",
            "event_key": "fallback",
            "caseContents": "foo incident",
            "alarmTime": "2026-04-04 10:00:00",
        }
        dedup_key = build_theme_dedup_key(topic, row)
        oracle_eid = build_theme_oracle_eid(topic, dedup_key)
        self.assertEqual(dedup_key, "JQ-002")
        self.assertEqual(oracle_eid, "juvenile_case:JQ-002")

    def test_window_dedup_since(self) -> None:
        topic = SimpleNamespace(dedup_mode="window", dedup_window_minutes=30)
        current_time = datetime(2026, 4, 4, 10, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        since = theme_dedup_since(topic, current_time)
        self.assertEqual(since, datetime(2026, 4, 4, 9, 30, 0))

    def test_topic_allows_row_when_bound_to_target_topic_codes(self) -> None:
        row = {"target_topic_codes": ["dxpt_u24"]}
        self.assertTrue(topic_allows_row(SimpleNamespace(theme_code="dxpt_u24"), row))
        self.assertFalse(topic_allows_row(SimpleNamespace(theme_code="dxpt_u36"), row))

    def test_topic_allows_row_without_target_topic_codes(self) -> None:
        self.assertTrue(topic_allows_row(SimpleNamespace(theme_code="dxpt_u24"), {}))


if __name__ == "__main__":
    unittest.main()
