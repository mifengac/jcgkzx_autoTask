from __future__ import annotations

from datetime import datetime
import os
from types import SimpleNamespace
import unittest

os.environ.setdefault("DATABASE_URL", "sqlite://")

from autotask_api.services.theme_adapters.dsjfx_case_list import DsjfxCaseListThemeAdapter
from autotask_api.services.theme_executor import (
    build_theme_dedup_key,
    build_theme_message,
    build_theme_oracle_eid,
    theme_dedup_since,
)


class ThemeAdapterAndExecutorTests(unittest.TestCase):
    def test_adapter_normalizes_row(self) -> None:
        adapter = DsjfxCaseListThemeAdapter()
        row = adapter._normalize_row(
            {
                "caseNo": "JQ-001",
                "callTime": "2026-04-04 09:00:00",
                "dutyDeptNo": "445302180000",
                "dutyDeptName": "测试派出所",
                "caseContents": "未成年人警情",
                "replies": "已派警",
            },
            "dsjfx_case_main",
            1,
        )
        self.assertEqual(row["event_key"], "JQ-001")
        self.assertEqual(row["case_no"], "JQ-001")
        self.assertEqual(row["sspcsdm"], "445302180000")
        self.assertEqual(row["xqdm"], "445302")
        self.assertEqual(row["message_vars"]["duty_dept_name"], "测试派出所")

    def test_build_theme_message_includes_hit_keyword(self) -> None:
        topic = SimpleNamespace(
            filter_expr_json='{"field":"caseContents","op":"contains_any","value":["坟地","林地"]}',
            message_template=SimpleNamespace(
                template_content="命中关键字：{命中关键字}\n地点：{occur_address}"
            ),
        )
        row = {
            "caseContents": "群众反映有人在坟地焚烧纸钱",
            "occur_address": "城郊坟地附近",
            "message_vars": {"case_no": "JQ-002"},
        }
        message = build_theme_message(topic, row)
        self.assertEqual(message, "命中关键字：报警内容→坟地\n地点：城郊坟地附近")

    def test_build_theme_dedup_key_and_eid(self) -> None:
        topic = SimpleNamespace(
            dedup_key_template="{hit_keyword}:{case_no}",
            theme_code="juvenile_case",
            filter_expr_json='{"field":"caseContents","op":"contains_any","value":["坟地","林地"]}',
        )
        row = {
            "case_no": "JQ-002",
            "event_key": "fallback",
            "caseContents": "群众反映有人在坟地焚烧纸钱",
        }
        dedup_key = build_theme_dedup_key(topic, row)
        oracle_eid = build_theme_oracle_eid(topic, dedup_key)
        self.assertEqual(dedup_key, "报警内容→坟地:JQ-002")
        self.assertEqual(oracle_eid, "juvenile_case:报警内容→坟地:JQ-002")

    def test_window_dedup_since(self) -> None:
        topic = SimpleNamespace(dedup_mode="window", dedup_window_minutes=30)
        current_time = datetime(2026, 4, 4, 10, 0, 0)
        since = theme_dedup_since(topic, current_time)
        self.assertEqual(since, datetime(2026, 4, 4, 9, 30, 0))


if __name__ == "__main__":
    unittest.main()
