from claude_history_mcp.utils import (
    parse_timestamp,
    scrub_surrogates,
)


def test_scrub_surrogates_normal():
    assert scrub_surrogates("hello world") == "hello world"


def test_scrub_surrogates_none():
    assert scrub_surrogates(None) is None


def test_scrub_surrogates_high_surrogate():
    s = "before\ud800after"
    result = scrub_surrogates(s)
    assert result is not None
    assert "\ud800" not in result
    assert "\ufffd" in result


def test_parse_timestamp_valid():
    assert parse_timestamp("2026-07-23T10:00:00Z") is not None


def test_parse_timestamp_none():
    assert parse_timestamp(None) is None


def test_parse_timestamp_invalid():
    assert parse_timestamp("garbage") is None
