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
    s = re.sub(r"[\ud800-\udfff]", "\ufffd", s)
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


# Model pricing per 1M tokens (input, output) in USD
# Source: https://platform.claude.com/docs/en/about-claude/pricing
# Last verified: 2026-07-27
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),  # Introductory pricing through Aug 31, 2026
    "claude-haiku-4-5": (1.0, 5.0),
}

DEFAULT_PRICING = (3.0, 15.0)  # Default to Sonnet pricing


def calculate_cost(model: str | None, input_tokens: int, output_tokens: int) -> float:
    """Calculate cost in USD for given model and token counts."""
    if not model:
        pricing = DEFAULT_PRICING
    else:
        # Match prefix or exact
        model_lower = (model or "").lower()
        pricing = next(
            (v for k, v in MODEL_PRICING.items() if model_lower.startswith(k)),
            DEFAULT_PRICING,
        )
    input_cost = (input_tokens / 1_000_000) * pricing[0]
    output_cost = (output_tokens / 1_000_000) * pricing[1]
    return round(input_cost + output_cost, 6)
