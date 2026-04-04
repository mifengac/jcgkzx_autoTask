from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from fastapi import HTTPException, status


class ThemeSourceLike(Protocol):
    source_type: str
    source_code: str


class ThemeSourceAdapter(Protocol):
    source_type: str

    def fetch(
        self,
        *,
        source: ThemeSourceLike,
        source_config: dict[str, Any],
        now: datetime,
        dry_run: bool,
    ) -> list[dict[str, Any]]:
        ...


_ADAPTERS: dict[str, ThemeSourceAdapter] = {}


def register_theme_source_adapter(adapter: ThemeSourceAdapter) -> None:
    _ADAPTERS[adapter.source_type] = adapter


def get_theme_source_adapter(source_type: str) -> ThemeSourceAdapter:
    adapter = _ADAPTERS.get(source_type)
    if adapter:
        return adapter
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported theme source_type: {source_type}",
    )
