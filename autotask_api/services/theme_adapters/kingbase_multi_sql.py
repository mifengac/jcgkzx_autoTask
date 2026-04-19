from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import create_engine, text

from autotask_api.config import get_settings
from autotask_api.services.theme_adapters.base import ThemeSourceLike, register_theme_source_adapter
from autotask_api.services.theme_adapters.db_sql_select import (
    DEFAULT_CHUNK_SIZE,
    DEFAULT_MAX_ROWS,
    DbSqlSelectThemeAdapter,
    _coerce_str_list,
    _resolve_env_value,
    _safe_str,
)


class KingbaseMultiSqlThemeAdapter(DbSqlSelectThemeAdapter):
    source_type = "kingbase_multi_sql"

    def fetch(
        self,
        *,
        source: ThemeSourceLike,
        source_config: dict[str, Any],
        now: datetime,
        dry_run: bool,
    ) -> list[dict[str, Any]]:
        del dry_run

        database_url = self._resolve_database_url(source_config)
        queries = self._resolve_queries(source_config, source.source_code)
        engine = create_engine(database_url, pool_pre_ping=True, future=True)
        rows: list[dict[str, Any]] = []
        row_index = 0

        try:
            with engine.connect() as connection:
                for query_index, query_config in enumerate(queries, start=1):
                    query_code = str(query_config["query_code"])
                    topic_codes = query_config["topic_codes"]
                    effective_config = self._merge_query_config(source_config, query_config)
                    query = self._resolve_query(effective_config, f"{source.source_code}/{query_code}")
                    begin_time, end_time = self._build_time_range(effective_config, now)
                    params = self._build_query_params(
                        source=source,
                        source_config=effective_config,
                        begin_time=begin_time,
                        end_time=end_time,
                    )
                    field_map = (
                        effective_config.get("field_map")
                        if isinstance(effective_config.get("field_map"), dict)
                        else {}
                    )
                    fetch_profile = (
                        effective_config.get("fetch_profile")
                        if isinstance(effective_config.get("fetch_profile"), dict)
                        else {}
                    )
                    chunk_size = max(1, int(fetch_profile.get("chunk_size") or DEFAULT_CHUNK_SIZE))
                    max_rows = max(1, int(fetch_profile.get("max_rows") or DEFAULT_MAX_ROWS))
                    query_row_count = 0

                    result = connection.execution_options(stream_results=True).execute(
                        text(query),
                        params,
                    )
                    while True:
                        batch = result.fetchmany(chunk_size)
                        if not batch:
                            break
                        for db_row in batch:
                            row_index += 1
                            query_row_count += 1
                            normalized = self._normalize_row(
                                raw_row=dict(db_row._mapping),
                                source_code=source.source_code,
                                index=row_index,
                                field_map=field_map,
                            )
                            normalized.update(
                                {
                                    "source_query_code": query_code,
                                    "source_query_index": query_index,
                                    "target_topic_codes": list(topic_codes),
                                }
                            )
                            message_vars = normalized.get("message_vars")
                            if isinstance(message_vars, dict):
                                message_vars.update(
                                    {
                                        "source_query_code": query_code,
                                        "source_query_index": query_index,
                                    }
                                )
                            rows.append(normalized)
                            if query_row_count >= max_rows:
                                break
                        if query_row_count >= max_rows:
                            break
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Theme source {source.source_code} Kingbase multi SQL query failed: {exc}",
            ) from exc
        finally:
            engine.dispose()

        return rows

    def _resolve_database_url(self, source_config: dict[str, Any]) -> str:
        del source_config
        settings = get_settings()
        theme_db_url = _resolve_env_value("THEME_DB_URL") or _safe_str(settings.theme_db_url)
        if theme_db_url:
            return theme_db_url

        database_url = _resolve_env_value("DATABASE_URL") or _safe_str(settings.database_url)
        if database_url:
            return database_url

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Theme source database URL is missing. "
                "Set THEME_DB_URL or DATABASE_URL in the environment."
            ),
        )

    def _resolve_queries(
        self,
        source_config: dict[str, Any],
        source_code: str,
    ) -> list[dict[str, Any]]:
        queries = source_config.get("queries")
        if not isinstance(queries, list) or not queries:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Theme source {source_code} queries must be a non-empty list.",
            )

        resolved: list[dict[str, Any]] = []
        seen_codes: set[str] = set()
        for index, item in enumerate(queries, start=1):
            if not isinstance(item, dict):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Theme source {source_code} query #{index} must be an object.",
                )

            query_code = str(item.get("query_code") or "").strip()
            if not query_code:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Theme source {source_code} query #{index} query_code is required.",
                )
            if query_code in seen_codes:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Theme source {source_code} query_code is duplicated: {query_code}.",
                )
            seen_codes.add(query_code)

            topic_codes = _coerce_str_list(item.get("topic_codes"))
            if not topic_codes:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Theme source {source_code} query {query_code} topic_codes is required.",
                )

            query = str(item.get("query") or "").strip()
            if not query:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Theme source {source_code} query {query_code} SQL is empty.",
                )

            resolved.append({**item, "query_code": query_code, "topic_codes": topic_codes})
        return resolved

    def _merge_query_config(
        self,
        source_config: dict[str, Any],
        query_config: dict[str, Any],
    ) -> dict[str, Any]:
        merged = dict(source_config)
        for key in ("query", "time_range", "fetch_profile", "field_map", "query_params"):
            if key not in query_config:
                continue
            if (
                key in {"time_range", "fetch_profile", "field_map", "query_params"}
                and isinstance(source_config.get(key), dict)
                and isinstance(query_config.get(key), dict)
            ):
                merged[key] = {**source_config[key], **query_config[key]}
            else:
                merged[key] = query_config[key]
        return merged


register_theme_source_adapter(KingbaseMultiSqlThemeAdapter())
