from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def now_shanghai() -> datetime:
    return datetime.now(SHANGHAI_TZ)


def now_shanghai_naive() -> datetime:
    return now_shanghai().replace(tzinfo=None)


def shanghai_date_str(days_ago: int = 0) -> str:
    return (now_shanghai().date() - timedelta(days=days_ago)).strftime("%Y-%m-%d")


def shanghai_datetime_str(days_ago: int = 0, *, end_of_day: bool = False) -> str:
    base = now_shanghai() - timedelta(days=days_ago)
    if end_of_day:
        return base.strftime("%Y-%m-%d 23:59:59")
    return base.strftime("%Y-%m-%d 00:00:00")


def to_shanghai_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(SHANGHAI_TZ).replace(tzinfo=None)
