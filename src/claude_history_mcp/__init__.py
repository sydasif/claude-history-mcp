"""Claude History MCP Server — Query your Claude Code session history."""

from pathlib import Path

from .cache import CacheManager
from .loader import load_all_projects, load_history_file
from .search import SearchEngine
from .utils import get_history_file

__all__ = ["get_cache_path", "initialize", "CacheManager", "SearchEngine"]


def get_cache_path() -> Path:
    """Return path to the SQLite cache database."""
    return Path.home() / ".claude" / "history.db"


def initialize(force: bool = False) -> SearchEngine:
    """Initialize the cache and return a ready SearchEngine.

    Loads all JSONL files from ~/.claude/projects/ and ~/.claude/history.jsonl
    into a SQLite cache at ~/.claude/history.db. Unchanged session
    files are skipped on subsequent calls (see loader.load_project); the
    global history.jsonl is always re-scanned but inserts are de-duplicated
    at the cache layer.
    """
    db_path = get_cache_path()
    cache = CacheManager(db_path)

    if force:
        cache.clear_all()

    # Load session transcripts
    load_all_projects(cache, force=force)

    # Load command history
    history_file = get_history_file()
    if history_file:
        load_history_file(history_file, cache)

    return SearchEngine(cache)
