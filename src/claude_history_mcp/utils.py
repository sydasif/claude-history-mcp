"""Shared utilities: surrogate handling, timestamp parsing, path helpers."""

import re
from datetime import datetime
from pathlib import Path


def scrub_surrogates(s: str | None) -> str | None:
    """Replace lone surrogates with U+FFFD for safe SQLite storage.

    Args:
        s: Input string that may contain lone surrogates.

    Returns:
        String with surrogates replaced by U+FFFD, or None if input was None.
    """
    if s is None:
        return None
    s = re.sub(r"[\ud800-\udbff]", "\ufffd", s)
    return s.encode("utf-8", errors="surrogateescape").decode("utf-8", errors="replace")


def parse_timestamp(ts: str | None) -> datetime | None:
    """Parse ISO 8601 timestamp to datetime. Returns None for missing/invalid.

    Returns naive UTC datetime for consistent comparison.

    Args:
        ts: ISO 8601 timestamp string (with or without Z suffix).

    Returns:
        Naive UTC datetime, or None if input is None or invalid.
    """
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        # Convert to naive UTC for consistent comparison
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return dt
    except (ValueError, AttributeError):
        return None


def get_claude_dir() -> Path:
    """Return ~/.claude directory.

    Returns:
        Path to the Claude Code directory.
    """
    return Path.home() / ".claude"


def get_projects_dir() -> Path:
    """Return ~/.claude/projects directory.

    Returns:
        Path to the Claude Code projects directory.
    """
    return get_claude_dir() / "projects"


def get_history_file() -> Path | None:
    """Return ~/.claude/history.jsonl if it exists.

    Returns:
        Path to the history file, or None if it doesn't exist.
    """
    path = get_claude_dir() / "history.jsonl"
    return path if path.exists() else None
