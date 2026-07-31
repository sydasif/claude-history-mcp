"""Shared SearchEngine singleton management."""

from __future__ import annotations

from .search import SearchEngine

_engine: SearchEngine | None = None


def get_engine() -> SearchEngine:
    global _engine
    if _engine is None:
        from . import initialize

        _engine = initialize()
    return _engine
