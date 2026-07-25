from __future__ import annotations

from datetime import datetime, timedelta
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SMS_GATEWAY_BASE_URL", "http://sms-gateway.test:5011")
os.environ.setdefault("SMS_GATEWAY_TOKEN", "test-token")
os.environ.setdefault("SMS_GATEWAY_MAX_RETRIES", "0")

from fastapi import HTTPException

from autotask_api.config import get_settings
from autotask_api.services import sms_gateway_client as client_mod
from autotask_api.services.sms_gateway_client import SmsGatewayClient
from autotask_api.services.theme_executor import theme_dedup_minutes_from_since
from autotask_api.services.time_utils import SHANGHAI_TZ


class SmsGatewayClientTests(unittest.TestCase):
    def setUp(self) -> None:
        get_settings.cache_clear()
        os.environ["SMS_GATEWAY_BASE_URL"] = "http://sms-gateway.test:5011"
        os.environ["SMS_GATEWAY_TOKEN"] = "test-token"
        os.environ["SMS_GATEWAY_MAX_RETRIES"] = "0"
        get_settings.cache_clear()
        client_mod._warned_deprecated_keys.clear()

    def tearDown(self) -> None:
        get_settings.cache_clear()

    def _client(self) -> SmsGatewayClient:
        return SmsGatewayClient()

    def _mock_response(
        self,
        *,
        status_code: int = 200,
        payload: dict | None = None,
        text: str = "",
    ) -> MagicMock:
        response = MagicMock()
        response.status_code = status_code
        response.text = text
        if payload is not None:
            response.json.return_value = payload
        else:
            response.json.side_effect = ValueError("not json")
        return response

    @patch("autotask_api.services.sms_gateway_client.requests.post")
    def test_inserted_maps_to_sent(self, mock_post: MagicMock) -> None:
        mock_post.return_value = self._mock_response(
            payload={"success": True, "inserted": 1, "skipped": 0, "failed": [], "total": 1}
        )
        outcome = self._client().send_one(
            mobile="13800138000",
            content="hello",
            eid="E1",
            biz="yfjcgkzx",
            dedup_minutes=30,
        )
        self.assertEqual(outcome.status, "sent")
        self.assertIsNone(outcome.error_message)
        kwargs = mock_post.call_args.kwargs
        self.assertEqual(kwargs["json"]["mobiles"], ["13800138000"])
        self.assertEqual(kwargs["json"]["dedup_minutes"], 30)
        self.assertNotIn("dedup_hours", kwargs["json"])
        self.assertEqual(kwargs["headers"]["X-API-Key"], "test-token")

    @patch("autotask_api.services.sms_gateway_client.requests.post")
    def test_skipped_maps_to_skipped_duplicate(self, mock_post: MagicMock) -> None:
        mock_post.return_value = self._mock_response(
            payload={"success": True, "inserted": 0, "skipped": 1, "failed": [], "total": 1}
        )
        outcome = self._client().send_one(
            mobile="13800138000",
            content="hello",
            eid="E1",
            biz="yfjcgkzx",
            dedup_minutes=30,
        )
        self.assertEqual(outcome.status, "skipped_duplicate")

    @patch("autotask_api.services.sms_gateway_client.requests.post")
    def test_failed_maps_with_reason(self, mock_post: MagicMock) -> None:
        mock_post.return_value = self._mock_response(
            payload={
                "success": False,
                "inserted": 0,
                "skipped": 0,
                "failed": [{"mobile": "13800138000", "eid": "E1", "reason": "bad mobile"}],
                "total": 1,
            }
        )
        outcome = self._client().send_one(
            mobile="13800138000",
            content="hello",
            eid="E1",
            biz="yfjcgkzx",
            dedup_minutes=30,
        )
        self.assertEqual(outcome.status, "failed")
        self.assertIn("bad mobile", outcome.error_message or "")

    @patch("autotask_api.services.sms_gateway_client.requests.post")
    def test_connection_error_raises_502(self, mock_post: MagicMock) -> None:
        import requests as req

        mock_post.side_effect = req.ConnectionError("refused")
        with self.assertRaises(HTTPException) as ctx:
            self._client().send_one(
                mobile="13800138000",
                content="hello",
                eid="E1",
                biz="yfjcgkzx",
                dedup_minutes=30,
            )
        self.assertEqual(ctx.exception.status_code, 502)
        self.assertIn("Failed to reach SMS gateway", str(ctx.exception.detail))

    @patch("autotask_api.services.sms_gateway_client.requests.post")
    def test_http_401_raises_502_with_reject_prefix(self, mock_post: MagicMock) -> None:
        mock_post.return_value = self._mock_response(
            status_code=401,
            payload={"detail": "unauthorized"},
        )
        with self.assertRaises(HTTPException) as ctx:
            self._client().send_one(
                mobile="13800138000",
                content="hello",
                eid="E1",
                biz="yfjcgkzx",
                dedup_minutes=30,
            )
        self.assertEqual(ctx.exception.status_code, 502)
        self.assertIn("rejected request (HTTP 401)", str(ctx.exception.detail))
        self.assertIn("unauthorized", str(ctx.exception.detail))

    @patch("autotask_api.services.sms_gateway_client.requests.post")
    def test_http_400_without_json_fields_falls_back_to_text(self, mock_post: MagicMock) -> None:
        mock_post.return_value = self._mock_response(
            status_code=400,
            payload={"other": "x"},
            text="plain validation error body",
        )
        # json returns dict without detail/message/error → should still try text if empty
        response = mock_post.return_value
        response.json.return_value = {"other": "x"}
        response.text = "plain validation error body"
        with self.assertRaises(HTTPException) as ctx:
            self._client().send_one(
                mobile="13800138000",
                content="hello",
                eid="E1",
                biz="yfjcgkzx",
                dedup_minutes=30,
            )
        self.assertIn("rejected request (HTTP 400)", str(ctx.exception.detail))
        self.assertIn("plain validation error body", str(ctx.exception.detail))

    @patch("autotask_api.services.sms_gateway_client.time.sleep")
    @patch("autotask_api.services.sms_gateway_client.requests.post")
    def test_retries_on_timeout_then_succeeds(
        self, mock_post: MagicMock, mock_sleep: MagicMock
    ) -> None:
        import requests as req

        os.environ["SMS_GATEWAY_MAX_RETRIES"] = "2"
        get_settings.cache_clear()
        mock_post.side_effect = [
            req.Timeout("timeout"),
            self._mock_response(
                payload={"success": True, "inserted": 1, "skipped": 0, "failed": [], "total": 1}
            ),
        ]
        outcome = self._client().send_one(
            mobile="13800138000",
            content="hello",
            eid="E1",
            biz="yfjcgkzx",
            dedup_minutes=30,
        )
        self.assertEqual(outcome.status, "sent")
        self.assertEqual(mock_post.call_count, 2)
        mock_sleep.assert_called()

    def test_resolve_biz_priority(self) -> None:
        client = self._client()
        self.assertEqual(client.resolve_biz({"sms_business_name": "custom_biz"}), "custom_biz")
        self.assertEqual(client.resolve_biz({}), "yfjcgkzx")

    def test_deprecated_keys_warn_once(self) -> None:
        client = self._client()
        with self.assertLogs(client_mod.logger, level="WARNING") as captured:
            client.resolve_biz({"sms_userid": "u1", "sms_password": "p1"})
            client.resolve_biz({"sms_userid": "u1", "sms_password": "p1"})
        # One warning per key, not per call.
        messages = "\n".join(captured.output)
        self.assertEqual(messages.count("sms_userid"), 1)
        self.assertEqual(messages.count("sms_password"), 1)


class ThemeDedupMinutesTests(unittest.TestCase):
    def test_none_since_uses_permanent_hours_times_sixty(self) -> None:
        now = datetime(2026, 7, 25, 12, 0, 0, tzinfo=SHANGHAI_TZ)
        minutes = theme_dedup_minutes_from_since(None, now, permanent_hours=87600)
        self.assertEqual(minutes, 87600 * 60)

    def test_window_round_to_minutes_no_ceil_to_hour(self) -> None:
        now = datetime(2026, 7, 25, 12, 0, 0, tzinfo=SHANGHAI_TZ)
        since = (now - timedelta(minutes=30)).replace(tzinfo=None)
        minutes = theme_dedup_minutes_from_since(since, now, permanent_hours=87600)
        self.assertEqual(minutes, 30)

    def test_window_minimum_one_minute(self) -> None:
        now = datetime(2026, 7, 25, 12, 0, 0, tzinfo=SHANGHAI_TZ)
        since = now.replace(tzinfo=None)  # zero delta → floor to 1
        minutes = theme_dedup_minutes_from_since(since, now, permanent_hours=87600)
        self.assertEqual(minutes, 1)


if __name__ == "__main__":
    unittest.main()
