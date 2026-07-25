from hashlib import sha1

from autotask_api.services.oracle_eid import (
    MAX_ORACLE_EID_BYTES,
    fit_oracle_eid,
)


def test_short_mdjf_eid_returned_unchanged():
    raw = "mdjf:9f70f785148a4f129a340a74a917bfb5:u72plus"
    assert len(raw.encode("utf-8")) == 45
    assert fit_oracle_eid(raw, prefix="mdjf") == raw


def test_oversize_transfer_reminder_converges_to_50_with_prefix():
    raw = "dxpt_transfer_reminder:249062a56d8c41839744fcb038c0a6b9:u72plus"
    assert len(raw.encode("utf-8")) == 63
    result = fit_oracle_eid(raw, prefix="dxpt_transfer_reminder")
    assert len(result.encode("utf-8")) == MAX_ORACLE_EID_BYTES
    # 17-byte ASCII prefix of "dxpt_transfer_reminder" is "dxpt_transfer_rem"
    assert result.startswith("dxpt_transfer_rem:")
    digest = sha1(raw.encode("utf-8")).hexdigest()[:32]
    assert result == f"dxpt_transfer_rem:{digest}"


def test_fit_is_deterministic():
    raw = "long_theme_code_here:" + ("x" * 80)
    a = fit_oracle_eid(raw, prefix="long_theme_code_here")
    b = fit_oracle_eid(raw, prefix="long_theme_code_here")
    assert a == b


def test_near_collision_keys_produce_different_eids():
    base = "yangyanjiduan_jq_topic:"
    a = fit_oracle_eid(base + ("a" * 40), prefix="yangyanjiduan_jq_topic")
    b = fit_oracle_eid(base + ("b" * 40), prefix="yangyanjiduan_jq_topic")
    assert a != b
    assert len(a.encode("utf-8")) == MAX_ORACLE_EID_BYTES
    assert len(b.encode("utf-8")) == MAX_ORACLE_EID_BYTES


def test_chinese_prefix_truncation_stays_valid_utf8_and_within_limit():
    prefix = "主题" * 20  # multi-byte; must not produce mojibake or oversize
    raw = f"{prefix}:{'k' * 80}"
    result = fit_oracle_eid(raw, prefix=prefix)
    # Multi-byte truncation may leave <17 prefix bytes; total must never exceed 50.
    assert len(result.encode("utf-8")) <= MAX_ORACLE_EID_BYTES
    result.encode("utf-8").decode("utf-8")
    assert ":" in result
    assert "\ufffd" not in result


def test_boundary_exactly_50_unchanged_51_hashed():
    exactly = "a" * 50
    assert fit_oracle_eid(exactly, prefix="a") == exactly

    over = "a" * 51
    result = fit_oracle_eid(over, prefix="prefix_for_hash")
    assert result != over
    assert len(result.encode("utf-8")) <= MAX_ORACLE_EID_BYTES
    # Long enough prefix fills the 17+1+32 layout exactly.
    long_prefix = "p" * 30
    result2 = fit_oracle_eid(over, prefix=long_prefix)
    assert len(result2.encode("utf-8")) == MAX_ORACLE_EID_BYTES
