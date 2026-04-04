from __future__ import annotations

import unittest

from autotask_api.services.theme_filter_engine import matches_filter_expr


class ThemeFilterEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.record = {
            "caseMarkNo": "01020201,0102020101",
            "caseContents": "报警人称精神障碍人员发病",
            "replies": "已联系社区民警",
            "raw_fields": {
                "dutyDeptName": "测试派出所",
            },
        }

    def test_matches_all_contains_any(self) -> None:
        expr = {
            "all": [
                {
                    "field": "caseMarkNo",
                    "op": "contains_any",
                    "value": ["01020201", "99999999"],
                }
            ]
        }
        self.assertTrue(matches_filter_expr(self.record, expr))

    def test_matches_any_regex(self) -> None:
        expr = {
            "any": [
                {"field": "caseContents", "op": "regex", "value": "精神障碍|发病"},
                {"field": "replies", "op": "regex", "value": "未命中"},
            ]
        }
        self.assertTrue(matches_filter_expr(self.record, expr))

    def test_supports_raw_fields_lookup(self) -> None:
        expr = {"field": "dutyDeptName", "op": "eq", "value": "测试派出所"}
        self.assertTrue(matches_filter_expr(self.record, expr))

    def test_not_expression(self) -> None:
        expr = {"not": {"field": "replies", "op": "contains", "value": "失败"}}
        self.assertTrue(matches_filter_expr(self.record, expr))


if __name__ == "__main__":
    unittest.main()
