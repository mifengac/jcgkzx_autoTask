from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from typing import Any

import requests
from fastapi import HTTPException, status

from autotask_api.config import get_settings


logger = logging.getLogger(__name__)

_DEPRECATED_CREDENTIAL_KEYS = ("sms_userid", "sms_password", "sms_userport")
# Process-level: warn once per deprecated key to avoid log storms in row loops.
_warned_deprecated_keys: set[str] = set()


@dataclass(frozen=True)
class SmsSendOutcome:
    status: str  # "sent" | "skipped_duplicate" | "failed"
    error_message: str | None = None


class SmsGatewayClient:
    """HTTP client for the internal oracle-sms-gateway service."""

    provider_name = "oracle_sms_gateway"

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = str(settings.sms_gateway_base_url or "").strip().rstrip("/")
        self._token = str(settings.sms_gateway_token or "").strip()
        self._timeout = float(settings.sms_gateway_timeout_seconds)
        self._max_retries = int(settings.sms_gateway_max_retries)
        if not self._base_url:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="SMS gateway base URL is not configured (SMS_GATEWAY_BASE_URL).",
            )
        if not self._token:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="SMS gateway token is not configured (SMS_GATEWAY_TOKEN).",
            )

    def resolve_biz(self, runtime_config: dict[str, Any]) -> str:
        for key in _DEPRECATED_CREDENTIAL_KEYS:
            value = runtime_config.get(key)
            if value not in (None, "") and key not in _warned_deprecated_keys:
                _warned_deprecated_keys.add(key)
                logger.warning(
                    "runtime_config key %s is ignored; SMS credentials and userport "
                    "are managed by oracle-sms-gateway (SMS_BIZ_USERPORTS).",
                    key,
                )

        biz = str(runtime_config.get("sms_business_name") or "").strip()
        if not biz:
            biz = str(get_settings().sms_gateway_biz or "").strip()
        if not biz:
            biz = "default"
        return biz

    def send_one(
        self,
        *,
        mobile: str,
        content: str,
        eid: str,
        biz: str,
        dedup_minutes: int,
    ) -> SmsSendOutcome:
        """Send one SMS. Always posts a single mobile so status maps 1:1.

        Retries are safe only when dedup_minutes > 0: the gateway (eid, mobile)
        window absorbs duplicate inserts if a timed-out request actually succeeded.
        """
        url = f"{self._base_url}/api/v1/sms/send"
        headers = {
            "X-API-Key": self._token,
            "Content-Type": "application/json",
        }
        payload = {
            "biz": biz,
            "eid": eid,
            "mobiles": [mobile],
            "content": content,
            "dedup_minutes": int(dedup_minutes),
        }

        response = self._post_with_retry(url, headers=headers, payload=payload)

        if response.status_code < 200 or response.status_code >= 300:
            detail = self._format_error_detail(response)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=detail,
            )

        try:
            data = response.json()
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="SMS gateway returned invalid JSON.",
            ) from exc

        if not isinstance(data, dict):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="SMS gateway returned unexpected response shape.",
            )

        failed = data.get("failed") or []
        if isinstance(failed, list) and failed:
            reason = ""
            first = failed[0]
            if isinstance(first, dict):
                reason = str(first.get("reason") or "").strip()
            return SmsSendOutcome(
                status="failed",
                error_message=reason or "SMS send failed",
            )

        inserted = int(data.get("inserted") or 0)
        skipped = int(data.get("skipped") or 0)
        if inserted == 1:
            return SmsSendOutcome(status="sent")
        if skipped == 1:
            return SmsSendOutcome(status="skipped_duplicate")

        return SmsSendOutcome(
            status="failed",
            error_message="Unexpected SMS gateway response",
        )

    def _post_with_retry(
        self,
        url: str,
        *,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> requests.Response:
        # Attempt 0 is the first try; then up to max_retries more on retryable errors.
        # Backoff sleeps: 1s, 3s, ... for successive retries.
        attempts = max(0, self._max_retries) + 1
        last_exc: Exception | None = None

        for attempt in range(attempts):
            try:
                response = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=(self._timeout, self._timeout),
                )
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exc = exc
                if attempt + 1 >= attempts:
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=f"Failed to reach SMS gateway: {exc}",
                    ) from exc
                sleep_s = 1 if attempt == 0 else 3
                time.sleep(sleep_s)
                continue
            except requests.RequestException as exc:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Failed to reach SMS gateway: {exc}",
                ) from exc

            # Retry 5xx; never retry 4xx (client/data errors).
            if 500 <= response.status_code < 600 and attempt + 1 < attempts:
                sleep_s = 1 if attempt == 0 else 3
                time.sleep(sleep_s)
                continue
            return response

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to reach SMS gateway: {last_exc}",
        )

    @staticmethod
    def _format_error_detail(response: requests.Response) -> str:
        code = response.status_code
        msg = ""
        try:
            body = response.json()
            if isinstance(body, dict):
                raw = body.get("detail") or body.get("message") or body.get("error")
                if raw is not None:
                    msg = str(raw).strip()
        except Exception:
            msg = ""
        if not msg:
            msg = (response.text or "").strip()[:200]

        if 400 <= code < 500:
            base = f"SMS gateway rejected request (HTTP {code})"
        else:
            base = f"SMS gateway unavailable (HTTP {code})"
        if msg:
            return f"{base}: {msg}"
        return base
