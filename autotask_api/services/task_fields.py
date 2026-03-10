from __future__ import annotations


EMPTY_DEDUP_KEY_EXPR_SENTINEL = "__EMPTY__"
EMPTY_TEXT_SENTINEL = "__EMPTY_TEXT__"


def normalize_dedup_key_expr_input(value: str | None) -> str:
    text = str(value or "").strip()
    return text or EMPTY_DEDUP_KEY_EXPR_SENTINEL


def normalize_dedup_key_expr_output(value: str | None) -> str:
    text = str(value or "").strip()
    if text == EMPTY_DEDUP_KEY_EXPR_SENTINEL:
        return ""
    return text


def normalize_non_null_text_input(value: str | None) -> str:
    text = str(value or "")
    return text if text else EMPTY_TEXT_SENTINEL


def normalize_non_null_text_output(value: str | None) -> str:
    text = str(value or "")
    if text == EMPTY_TEXT_SENTINEL:
        return ""
    return text
