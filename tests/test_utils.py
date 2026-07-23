from pathlib import Path

from claude_history_mcp.utils import (
    epoch_ms_to_datetime,
    get_claude_dir,
    get_projects_dir,
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
    assert "\ud800" not in result
    assert "\ufffd" in result


def test_parse_timestamp_valid():
    assert parse_timestamp("2026-07-23T10:00:00Z") is not None


def test_parse_timestamp_none():
    assert parse_timestamp(None) is None


def test_parse_timestamp_invalid():
    assert parse_timestamp("garbage") is None


def test_epoch_ms_to_datetime():
    dt = epoch_ms_to_datetime(1784532628943)
    assert dt.year >= 2026


def test_get_claude_dir():
    assert get_claude_dir() == Path.home() / ".claude"


def test_get_projects_dir():
    assert get_projects_dir() == Path.home() / ".claude" / "projects"
