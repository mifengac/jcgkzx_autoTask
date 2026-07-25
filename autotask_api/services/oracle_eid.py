"""Converge business EIDs to Oracle yfgadb.dfsdl.EID VARCHAR2(50 BYTE).

Critical: EIDs that already fit in 50 UTF-8 bytes MUST be returned unchanged.
Hashing/truncating short EIDs would break gateway dedup history and cause
mass re-sends of previously delivered messages.
"""

from __future__ import annotations

from hashlib import sha1


MAX_ORACLE_EID_BYTES = 50
_EID_HASH_HEX = 32
_EID_PREFIX_BYTES = MAX_ORACLE_EID_BYTES - 1 - _EID_HASH_HEX  # 17


def _byte_len(value: str) -> int:
    return len(value.encode("utf-8"))


def _truncate_utf8_bytes(value: str, limit: int) -> str:
    """Truncate to at most `limit` UTF-8 bytes without splitting a code point."""
    if limit <= 0:
        return ""
    encoded = value.encode("utf-8")
    if len(encoded) <= limit:
        return value
    return encoded[:limit].decode("utf-8", errors="ignore")


def fit_oracle_eid(raw_eid: str, *, prefix: str) -> str:
    """Return an EID that fits in 50 UTF-8 bytes.

    - If raw_eid already fits, return it unchanged (including every character).
    - Otherwise: ``{prefix_truncated_to_17_bytes}:{sha1(raw_eid)[:32]}``
      (17 + 1 + 32 = 50). Hash input is the full raw_eid so uniqueness holds
      even when prefixes collide after truncation.
    """
    raw = str(raw_eid or "")
    if _byte_len(raw) <= MAX_ORACLE_EID_BYTES:
        return raw

    digest = sha1(raw.encode("utf-8")).hexdigest()[:_EID_HASH_HEX]
    head = _truncate_utf8_bytes(str(prefix or ""), _EID_PREFIX_BYTES)
    return f"{head}:{digest}"
