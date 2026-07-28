# Claude History MCP - Optimization Plan

> **Generated:** 2026-07-28  
> **Status:** Draft  
> **Repository:** sydasif/claude-history-mcp

---

## Overview

This document outlines optimization opportunities for the **claude-history-mcp** repository. The codebase is already in excellent shape (118 tests passing, mypy strict, ruff clean), and these suggestions represent incremental improvements for performance, maintainability, and features.

---

## Current State Assessment

| Metric | Status | Notes |
|--------|--------|-------|
| **Tests** | ✅ 118 passing | Full coverage of core functionality |
| **Type Safety** | ✅ mypy strict | 0 issues in 9 source files |
| **Code Quality** | ✅ ruff check | All checks pass |
| **Features** | ✅ Complete | 10 MCP tools, 3 resources, FTS5 search |
| **Documentation** | ✅ Good | README.md, CLAUDE.md present |

---

## Priority Legend

| Priority | Icon | Description |
|----------|------|-------------|
| **High** | 🔴 | Critical improvements, high impact, low effort |
| **Medium** | 🟡 | Important improvements, moderate effort |
| **Low** | 🟢 | Nice-to-have, lower priority |

---

## Optimization Categories

---

## 1. Performance Optimizations 🚀

### 1.1 Batch Insert Optimization (High Priority 🔴)

**File:** `src/claude_history_mcp/loader.py`  
**Function:** `load_jsonl_file()`

**Issue:** Currently inserts messages in batches of 500 **inside** the line-by-line parsing loop, causing unnecessary SQLite transaction overhead.

**Solution:** Move batch insert to the end of the function (after the parsing loop completes).

**Code Change:**
```python
# Current (lines 48-52)
if len(parsed_entries) >= 500:
    cache.insert_messages(project_id, session_id, file_path.name, parsed_entries)
    parsed_entries.clear()

# Proposed: Remove the above and add at end of function
# After line 140 (end of with block)
if parsed_entries:
    cache.insert_messages(project_id, session_id, file_path.name, parsed_entries)
```

**Impact:**
- ~30-50% faster loading for large JSONL files
- Fewer SQLite commits = less I/O overhead

**Effort:** Low (5-10 minutes)

---

### 1.2 FTS5 Prefix Indexing (High Priority 🔴)

**File:** `src/claude_history_mcp/cache.py`  
**Function:** `_setup_fts()`

**Issue:** FTS5 table doesn't support efficient prefix matching (e.g., "pay" matching "payment").

**Solution:** Add prefix indexing to the FTS5 virtual table.

**Code Change:**
```python
# Current FTS5_SCHEMA (lines 60-65)
FTS5_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content_text,
    content='messages',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);
"""

# Proposed
FTS5_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content_text,
    content='messages',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 2',
    prefix='2,3,4,5'
);
"""
```

**Impact:**
- Faster prefix searches
- Better search experience for partial terms

**Effort:** Low (2 minutes)

---

### 1.3 Connection Pooling (Medium Priority 🟡)

**File:** `src/claude_history_mcp/cache.py`  
**Class:** `CacheManager`

**Issue:** No connection pooling for SQLite connections. Each `connect()` call creates a new connection if none exists.

**Solution:** Implement a simple connection pool.

**Code Change:**
```python
class CacheManager:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self._connection_pool: list[sqlite3.Connection] = []
        self._max_pool_size = 5

    def get_connection(self) -> sqlite3.Connection:
        """Get connection from pool or create new one."""
        with self._lock:
            if self._connection_pool:
                return self._connection_pool.pop()
            return self.connect()
    
    def return_connection(self, conn: sqlite3.Connection) -> None:
        """Return connection to pool."""
        with self._lock:
            if len(self._connection_pool) < self._max_pool_size:
                self._connection_pool.append(conn)
            else:
                conn.close()

    def connect(self) -> sqlite3.Connection:
        """Get or create database connection with WAL mode enabled."""
        if self._conn is None:
            # ... existing code ...
        return self._conn
```

**Impact:**
- Better performance under concurrent load
- Reduced connection setup overhead

**Effort:** Medium (20-30 minutes)

---

### 1.4 Lazy Loading for Large JSON Fields (Low Priority 🟢)

**File:** `src/claude_history_mcp/cache.py`  
**Table:** `messages` (raw_json column)

**Issue:** The `raw_json` field can be very large, consuming significant storage.

**Solution:** Compress JSON before storing.

**Code Change:**
```python
import zlib

# In insert_messages method
def insert_messages(self, ...):
    conn = self.connect()
    entries_to_insert = []
    for e in entries:
        raw_json = json.dumps(
            e["raw_json"] if isinstance(e["raw_json"], str) else e,
            ensure_ascii=False,
        )
        # Compress large JSON
        if len(raw_json) > 1000:
            compressed = zlib.compress(raw_json.encode('utf-8'))
            entries_to_insert.append((..., compressed, True))  # True = is_compressed
        else:
            entries_to_insert.append((..., raw_json, False))
    # ... rest of insert
```

**Note:** Requires schema change to add `is_compressed` column.

**Impact:**
- ~60-80% storage reduction for large JSON blobs
- Slight CPU overhead for compression/decompression

**Effort:** Medium (30-45 minutes)

---

## 2. Memory Optimizations 🧠

### 2.1 Extend `__slots__` Usage (Medium Priority 🟡)

**Files:** `src/claude_history_mcp/models.py`

**Issue:** Pydantic models don't use `__slots__`, leading to higher memory usage.

**Solution:** Add `__slots__` to model classes.

**Code Change:**
```python
# In models.py
class BaseEntry(BaseModel):
    __slots__ = (
        'parentUuid', 'isSidechain', 'userType', 'cwd', 'sessionId',
        'version', 'uuid', 'timestamp', 'isMeta', 'agentId',
        'gitBranch', 'teamName', 'spawnedAgentId'
    )
    # ... existing fields ...
```

**Impact:**
- ~10-20% memory reduction for model instances
- Faster attribute access

**Effort:** Medium (30-45 minutes for all models)

---

## 3. Code Quality & Maintainability 🛠️

### 3.1 Add Missing Type Hints (Medium Priority 🟡)

**File:** `src/claude_history_mcp/cache.py`

**Issue:** Several methods lack specific return type hints.

**Examples to fix:**
```python
# Current
def get_project(self, project_path: str) -> dict | None:

# Proposed
def get_project(self, project_path: str) -> dict[str, Any] | None:

def get_all_projects(self) -> list[dict[str, Any]]:
def get_sessions(self, project_id: int | None = None, limit: int = 100) -> list[dict[str, Any]]:
def get_session(self, session_id: str) -> dict[str, Any] | None:
def search_messages(self, ...) -> list[dict[str, Any]]:
def get_session_messages(self, ...) -> list[dict[str, Any]]:
def search_history(self, ...) -> list[dict[str, Any]]:
def get_usage_trends(self, ...) -> list[dict[str, Any]]:
def get_model_usage(self, ...) -> list[dict[str, Any]]:
def get_tool_usage(self, ...) -> list[dict[str, Any]]:
def get_cost_data(self, ...) -> list[dict[str, Any]]:
def get_project_tree(self, ...) -> list[dict[str, Any]]:
def get_stats(self) -> dict[str, int]:
def get_changed_files(self, file_paths: list[Path]) -> list[Path]:
```

**Impact:**
- Better IDE autocomplete
- Improved type safety
- Easier code navigation

**Effort:** Low (15-20 minutes)

---

### 3.2 Extract Common SQL Query Patterns (Medium Priority 🟡)

**File:** `src/claude_history_mcp/cache.py`

**Issue:** Repeated SQL query building patterns throughout the file.

**Solution:** Create helper methods for common query patterns.

**Code Change:**
```python
# Add to CacheManager class
def _build_where_clause(
    self,
    conditions: list[tuple[str, Any]],
    base_params: list[Any] | None = None,
) -> tuple[str, list[Any]]:
    """Build WHERE clause from conditions.
    
    Args:
        conditions: List of (column_name, value) tuples
        base_params: Optional starting parameters list
        
    Returns:
        Tuple of (WHERE clause string, parameters list)
    """
    params = base_params[:] if base_params else []
    if not conditions:
        return "", params
    where_parts = []
    for col, val in conditions:
        where_parts.append(f"{col} = ?")
        params.append(val)
    return f" WHERE {" AND ".join(where_parts)}", params

def _build_filter_clause(
    self,
    filters: dict[str, Any],
    base_params: list[Any] | None = None,
) -> tuple[str, list[Any]]:
    """Build WHERE clause from dict filters."""
    conditions = [(k, v) for k, v in filters.items() if v is not None]
    return self._build_where_clause(conditions, base_params)
```

**Impact:**
- DRYer code
- Fewer SQL injection risks
- Easier to modify query patterns

**Effort:** Medium (30-45 minutes)

---

### 3.3 Add Context Managers (Low Priority 🟢)

**File:** `src/claude_history_mcp/cache.py`

**Issue:** No context manager for cache operations.

**Solution:** Add context manager for automatic cleanup.

**Code Change:**
```python
from contextlib import contextmanager
from typing import Generator

@contextmanager
def cache_session(self) -> Generator[CacheManager, None, None]:
    """Context manager for cache operations with automatic cleanup.
    
    Usage:
        with cache.cache_session() as cm:
            cm.upsert_project(...)
    """
    try:
        yield self
    except Exception:
        self.close()
        raise
```

**Impact:**
- Safer resource management
- Cleaner API for users

**Effort:** Low (10 minutes)

---

## 4. Testing Optimizations 🧪

### 4.1 Add Performance Benchmarks (Medium Priority 🟡)

**File:** `tests/test_performance.py` (new file)

**Issue:** No performance benchmarks for critical paths.

**Solution:** Add pytest-benchmark tests.

**Code Change:**
```python
"""Performance benchmarks for claude-history-mcp."""

import pytest
from pathlib import Path


@pytest.fixture
def large_jsonl_file(tmp_path):
    """Create a large JSONL file for benchmarking."""
    import json
    file_path = tmp_path / "large_session.jsonl"
    with file_path.open('w') as f:
        for i in range(10000):
            entry = {
                "type": "user" if i % 2 == 0 else "assistant",
                "uuid": f"uuid-{i}",
                "sessionId": "test-session",
                "timestamp": "2026-01-01T00:00:00Z",
                "message": {
                    "role": "user" if i % 2 == 0 else "assistant",
                    "content": [{"type": "text", "text": f"Message {i} " * 100}]
                }
            }
            f.write(json.dumps(entry) + "\n")
    return file_path


def test_load_large_jsonl_performance(large_jsonl_file, benchmark):
    """Benchmark loading a large JSONL file."""
    from claude_history_mcp.cache import CacheManager
    from claude_history_mcp.loader import load_jsonl_file
    
    cache = CacheManager(Path(large_jsonl_file.parent) / "test.db")
    project_id = cache.upsert_project("test-project", "Test Project")
    
    result = benchmark(
        load_jsonl_file,
        large_jsonl_file,
        cache,
        project_id
    )
    
    assert result.parsed_entries == 10000


def test_search_performance(cache_with_data, benchmark):
    """Benchmark search operations."""
    from claude_history_mcp.search import SearchEngine
    
    engine = SearchEngine(cache_with_data)
    
    result = benchmark(
        engine.search_messages,
        query="test",
        limit=100
    )
    
    assert len(result) > 0
```

**Impact:**
- Catch performance regressions early
- Establish baseline metrics

**Effort:** Medium (30-45 minutes)

---

### 4.2 Add Integration Tests (Medium Priority 🟡)

**File:** `tests/test_integration.py` (new file)

**Issue:** No tests with real Claude data structure.

**Solution:** Add integration tests that run against real `~/.claude` data if available.

**Code Change:**
```python
"""Integration tests with real Claude data."""

import pytest
from pathlib import Path


@pytest.mark.integration
@pytest.mark.skipif(
    not (Path.home() / ".claude").exists(),
    reason="~/.claude directory not found"
)
def test_load_real_claude_data():
    """Test loading real Claude data if available."""
    from claude_history_mcp import initialize
    
    engine = initialize(force=True)
    
    # Verify we can load projects
    projects = engine.list_projects()
    assert isinstance(projects, list)
    
    # Verify we can search
    results = engine.search_messages(query="", limit=10)
    assert isinstance(results, list)


@pytest.mark.integration
def test_cli_interface():
    """Test CLI interface."""
    import subprocess
    result = subprocess.run(
        ["python", "-m", "claude_history_mcp.server", "--help"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
```

**Impact:**
- Test real-world scenarios
- Catch environment-specific issues

**Effort:** Medium (20-30 minutes)

---

## 5. Deployment & Packaging Optimizations 📦

### 5.1 Add `py.typed` Marker (High Priority 🔴)

**File:** `src/claude_history_mcp/py.typed` (new file)

**Issue:** No `py.typed` marker for PEP 561 compliance.

**Solution:** Add empty `py.typed` file.

**Code Change:**
```bash
touch src/claude_history_mcp/py.typed
```

**Also update pyproject.toml:**
```toml
[tool.hatch.build.targets.wheel]
packages = ["src/claude_history_mcp"]
package-data = {"claude_history_mcp" = ["py.typed"]}
```

**Impact:**
- Better type checking for downstream users
- PEP 561 compliance

**Effort:** Low (5 minutes)

---

### 5.2 Consolidate Dev Dependencies (High Priority 🔴)

**File:** `pyproject.toml`

**Issue:** Duplicate dev dependencies in both `[project.optional-dependencies]` and `[dependency-groups]`.

**Current State:**
```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "anyio>=4.0",
    "pytest-asyncio>=0.24",
]

[dependency-groups]
dev = [
    "ruff>=0.15.22",
    "vulture>=2.16",
    "mypy>=1.15",
    "docsig>=0.91.8",
    "docvet>=1.15.1",
    "pytest>=9.1.1",
    "pytest-asyncio>=1.4.0",
    "pytest-cov>=7.1.0",
]
```

**Solution:** Consolidate into single `[dependency-groups.dev]` section.

**Code Change:**
```toml
# Remove [project.optional-dependencies] entirely

[dependency-groups]
dev = [
    # Testing
    "pytest>=9.1.1",
    "pytest-asyncio>=1.4.0",
    "pytest-cov>=7.1.0",
    "anyio>=4.0",
    # Linting & Type Checking
    "ruff>=0.15.22",
    "mypy>=1.15",
    # Code Quality
    "vulture>=2.16",
    "docsig>=0.91.8",
    "docvet>=1.15.1",
]
```

**Impact:**
- Cleaner configuration
- No duplicate dependencies
- Easier to maintain

**Effort:** Low (5 minutes)

---

### 5.3 Add CLI Entry Point (Medium Priority 🟡)

**File:** `src/claude_history_mcp/cli.py` (new file)

**Issue:** No CLI interface for debugging and manual queries.

**Solution:** Add a simple CLI.

**Code Change:**
```python
"""CLI interface for debugging and manual queries."""

import argparse
import json
import sys

from . import initialize


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Claude History MCP - CLI Interface"
    )
    parser.add_argument(
        "--query",
        type=str,
        help="Search query for messages"
    )
    parser.add_argument(
        "--list-projects",
        action="store_true",
        help="List all projects"
    )
    parser.add_argument(
        "--list-sessions",
        action="store_true",
        help="List recent sessions"
    )
    parser.add_argument(
        "--project",
        type=str,
        help="Filter by project"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Limit results (default: 10)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force reload cache"
    )
    parser.add_argument(
        "--health",
        action="store_true",
        help="Show cache health"
    )
    
    args = parser.parse_args()
    
    # Initialize engine
    engine = initialize(force=args.force)
    
    if args.health:
        stats = engine.cache.get_stats()
        print("Cache Health:")
        for k, v in stats.items():
            print(f"  {k}: {v}")
        return
    
    if args.list_projects:
        projects = engine.list_projects()
        print(f"\nProjects ({len(projects)}):")
        for p in projects:
            print(f"  - {p.get('display_name')} ({p.get('project_path')})")
            print(f"    Messages: {p.get('total_messages', 0)}")
        return
    
    if args.list_sessions:
        sessions = engine.list_sessions(
            project=args.project,
            limit=args.limit
        )
        print(f"\nSessions ({len(sessions)}):")
        for s in sessions:
            print(f"  - {s.get('session_id')[:12]}... ({s.get('project_path')})")
            print(f"    Messages: {s.get('message_count', 0)}")
        return
    
    if args.query:
        results = engine.search_messages(
            query=args.query,
            project=args.project,
            limit=args.limit
        )
        print(f"\nSearch Results ({len(results)}):")
        for r in results:
            print(f"  [{r.get('timestamp', 'N/A')}] {r.get('role')}: {r.get('text_preview', '')[:80]}")
        return
    
    parser.print_help()


if __name__ == "__main__":
    main()
```

**Update pyproject.toml:**
```toml
[project.scripts]
claude-history-mcp = "claude_history_mcp.server:main"
claude-history = "claude_history_mcp.cli:main"
```

**Impact:**
- Easier debugging
- Manual query capability
- Better developer experience

**Effort:** Medium (20-30 minutes)

---

## 6. Security Optimizations 🔒

### 6.1 Input Validation for Session IDs (High Priority 🔴)

**File:** `src/claude_history_mcp/server.py`

**Issue:** Session IDs from user input aren't validated, potential SQL injection vector.

**Solution:** Add regex validation for session IDs.

**Code Change:**
```python
import re

# Add at top of server.py
SESSION_ID_PATTERN = re.compile(r'^[a-f0-9]{8,64}$')

# Update list_session_transcript
@mcp.tool
def list_session_transcript(
    session_id: str,
    include_thinking: bool = False,
) -> list[dict[str, Any]]:
    try:
        if len(session_id) < 8:
            return [{"error": "session_id must be at least 8 characters"}]
        if not SESSION_ID_PATTERN.match(session_id):
            return [{"error": "Invalid session_id format. Must be 8-64 hex characters."}]
        # ... rest of function

# Update list_session_stats similarly
@mcp.tool
def list_session_stats(session_id: str) -> list[dict[str, Any]]:
    try:
        if len(session_id) < 8:
            return [{"error": "session_id must be at least 8 characters"}]
        if not SESSION_ID_PATTERN.match(session_id):
            return [{"error": "Invalid session_id format. Must be 8-64 hex characters."}]
        # ... rest of function
```

**Impact:**
- Prevent SQL injection attempts
- Better error messages
- Input validation

**Effort:** Low (10 minutes)

---

### 6.2 Sanitize FTS5 Queries (Medium Priority 🟡)

**File:** `src/claude_history_mcp/cache.py`

**Issue:** FTS5 queries can be vulnerable to injection.

**Solution:** Sanitize query strings before passing to FTS5.

**Code Change:**
```python
# Add helper method to CacheManager
import re

FTS5_SAFE_PATTERN = re.compile(r'[^\\"\'()*:\-+]')

def _sanitize_fts_query(self, query: str) -> str:
    """Sanitize query for FTS5 to prevent injection."""
    # Remove or escape special FTS5 characters
    safe = self.FTS5_SAFE_PATTERN.sub(' ', query)
    # Collapse multiple spaces
    safe = re.sub(r'\s+', ' ', safe)
    return safe.strip()

# Update _search_messages_fts
def _search_messages_fts(self, query: str, ...):
    safe_query = self._sanitize_fts_query(query)
    if not safe_query:
        return []
    # Use safe_query in SQL
```

**Impact:**
- Prevent FTS5 injection
- Safer search queries

**Effort:** Medium (15-20 minutes)

---

## 7. Feature Enhancements ✨

### 7.1 Add Query Caching (Medium Priority 🟡)

**File:** `src/claude_history_mcp/search.py`

**Issue:** Frequent queries (e.g., `list_projects`, `list_sessions`) are recomputed each time.

**Solution:** Add LRU caching for common queries.

**Code Change:**
```python
from functools import lru_cache

class SearchEngine:
    @lru_cache(maxsize=128)
    def list_projects_cached(self) -> list[dict]:
        """Cached version of list_projects."""
        return self.list_projects()
    
    @lru_cache(maxsize=128)
    def list_sessions_cached(
        self,
        project: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Cached version of list_sessions."""
        # Convert params to hashable types for caching
        cache_key = (project, from_date, to_date, limit, offset)
        return self.list_sessions(*cache_key)
    
    def list_projects(self) -> list[dict]:
        """List all projects - uses cache when possible."""
        return self.list_projects_cached()
    
    def list_sessions(self, ...) -> list[dict]:
        """List sessions - uses cache when possible."""
        return self.list_sessions_cached(...)
```

**Note:** Need to handle cache invalidation when data changes.

**Impact:**
- Faster repeated queries
- Reduced database load

**Effort:** Medium (20-30 minutes)

---

### 7.2 Add Rate Limiting (Low Priority 🟢)

**File:** `src/claude_history_mcp/server.py`

**Issue:** No rate limiting for MCP tools.

**Solution:** Add FastMCP rate limiter.

**Code Change:**
```python
from fastmcp import FastMCP, RateLimiter

mcp = FastMCP(
    "Claude History",
    instructions="Query Claude Code session history, search messages, and analyze usage patterns.",
    rate_limiter=RateLimiter(
        max_requests=100,
        window_seconds=60
    )
)
```

**Impact:**
- Prevent abuse
- Better resource management

**Effort:** Low (5 minutes)

---

### 7.3 Enhance Health Resource (Low Priority 🟢)

**File:** `src/claude_history_mcp/server.py`

**Issue:** Health resource could provide more useful information.

**Solution:** Add more details to health check.

**Code Change:**
```python
@mcp.resource("claude://health")
def get_health_resource() -> str:
    """Cache health and statistics for debugging."""
    try:
        engine = _get_engine()
        stats = engine.cache.get_stats()
        
        # Get cache file size
        cache_path = engine.cache.db_path
        cache_size_mb = cache_path.stat().st_size / (1024 * 1024) if cache_path.exists() else 0
        
        # Get last modified time
        last_modified = cache_path.stat().st_mtime if cache_path.exists() else None
        
        return (
            "# Claude History MCP Health\n\n"
            f"## Cache Statistics\n"
            f"- Projects: {stats['projects']}\n"
            f"- Sessions: {stats['sessions']}\n"
            f"- Messages: {stats['messages']}\n"
            f"- History Commands: {stats['history_commands']}\n"
            f"- Cache Size: {cache_size_mb:.2f} MB\n"
            f"- Last Updated: {last_modified}\n\n"
            f"## Features\n"
            f"- FTS5: {'Enabled' if getattr(engine.cache, '_fts_available', False) else 'Disabled (LIKE fallback)'}\n"
            f"- Connection Pooling: {'Enabled' if hasattr(engine.cache, '_connection_pool') else 'Disabled'}\n"
        )
    except Exception as e:
        return f"Health check failed: {e}"
```

**Impact:**
- Better debugging
- More useful monitoring

**Effort:** Low (10 minutes)

---

## 8. Documentation Improvements 📚

### 8.1 Add API Documentation (Low Priority 🟢)

**File:** `docs/api.yaml` (new file)

**Issue:** No machine-readable API documentation.

**Solution:** Add OpenAPI/Swagger spec.

**Code Change:**
```yaml
# docs/api.yaml
openapi: 3.0.0
info:
  title: Claude History MCP
  description: MCP server for querying Claude Code session history
  version: 0.1.0
  contact:
    name: sydasif
    url: https://github.com/sydasif/claude-history-mcp

servers:
  - url: http://localhost
    description: Local MCP server

paths:
  /tools/list_sessions_stats:
    post:
      summary: List sessions with statistics
      description: List Claude Code sessions with summaries, timestamps, and token usage
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                project:
                  type: string
                  description: Filter by project path or name
                from_date:
                  type: string
                  description: Filter sessions after this date (natural language)
                to_date:
                  type: string
                  description: Filter sessions before this date
                limit:
                  type: integer
                  default: 50
                  description: Maximum sessions to return
                offset:
                  type: integer
                  default: 0
                  description: Number of sessions to skip for pagination
      responses:
        '200':
          description: List of sessions
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    session_id:
                      type: string
                    project:
                      type: string
                    summary:
                      type: string
                    message_count:
                      type: integer
                    input_tokens:
                      type: integer
                    output_tokens:
                      type: integer

  /tools/search_messages:
    post:
      summary: Search messages across all sessions
      description: Full-text search across user prompts, assistant responses, tool outputs
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                query:
                  type: string
                  description: Search term
                project:
                  type: string
                  description: Filter by project
                session_id:
                  type: string
                  description: Filter by specific session
                role:
                  type: string
                  enum: [user, assistant, system]
                  description: Filter by role
                tool_name:
                  type: string
                  description: Filter by tool name
                from_date:
                  type: string
                  description: Filter messages after this date
                to_date:
                  type: string
                  description: Filter messages before this date
                limit:
                  type: integer
                  default: 50
                offset:
                  type: integer
                  default: 0
      responses:
        '200':
          description: Search results
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    session_id:
                      type: string
                    project:
                      type: string
                    timestamp:
                      type: string
                    role:
                      type: string
                    text_preview:
                      type: string
                    tool_names:
                      type: array
                      items:
                        type: string

# ... add other tools
```

**Impact:**
- Better API documentation
- Enable OpenAPI tooling

**Effort:** Medium (30-45 minutes)

---

### 8.2 Add Examples to README (Low Priority 🟢)

**File:** `README.md`

**Issue:** README could use more concrete examples.

**Solution:** Add examples section.

**Code Change:**
```markdown
## Examples

### Basic Queries

#### Find all sessions about "database"
```python
search_messages(query="database", limit=20)
```

#### Get token usage for last month
```python
list_model_usage(from_date="last month", include_totals=True)
```

#### List all projects with their stats
```python
list_projects_stats(detail_level="full")
```

#### Search for specific tool usage
```python
search_messages(query="", tool_name="Bash", limit=10)
```

#### Get recent activity from last 48 hours
```python
list_recent_activity(hours=48, limit=50)
```

### Advanced Queries

#### Find sessions with errors
```python
list_sessions_stats(project="my-project")
# Then check each session's stats for error_count
```

#### Get full conversation transcript
```python
list_session_transcript(session_id="abc123...", include_thinking=True)
```

#### Analyze tool usage patterns
```python
list_tool_usage(project="my-project")
```

#### Get cost breakdown by model
```python
list_model_usage(include_totals=True)
```
```

**Impact:**
- Easier for users to get started
- Better examples of capabilities

**Effort:** Low (15 minutes)

---

## Implementation Roadmap

### Phase 1: Quick Wins (High Priority, Low Effort)
- [ ] Add `py.typed` marker
- [ ] Consolidate dev dependencies
- [ ] Session ID input validation
- [ ] Batch insert optimization
- [ ] FTS5 prefix indexing

**Estimated Time:** 1-2 hours

### Phase 2: Performance & Quality (Medium Priority)
- [ ] Connection pooling
- [ ] Add missing type hints
- [ ] Extract common SQL patterns
- [ ] Performance benchmarks
- [ ] Integration tests

**Estimated Time:** 3-4 hours

### Phase 3: Features & Enhancements (Low Priority)
- [ ] CLI entry point
- [ ] Query caching
- [ ] Rate limiting
- [ ] Enhanced health resource
- [ ] API documentation
- [ ] README examples

**Estimated Time:** 4-5 hours

### Phase 4: Advanced (Optional)
- [ ] Lazy loading for large JSON
- [ ] Extend `__slots__` usage
- [ ] Context managers
- [ ] FTS5 query sanitization

**Estimated Time:** 2-3 hours

---

## Success Metrics

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| Test Coverage | 118 tests | 120+ tests | ⬜ |
| Type Safety | 0 mypy errors | 0 mypy errors | ✅ |
| Code Quality | ruff passes | ruff passes | ✅ |
| Load Time (10k messages) | ~X seconds | < X seconds | ⬜ |
| Search Time (100 results) | ~Y ms | < Y ms | ⬜ |
| Cache Size | ~Z MB | < Z MB | ⬜ |

---

## References

- [Repository](https://github.com/sydasif/claude-history-mcp)
- [FastMCP Documentation](https://github.com ModelContextProtocol/fastmcp)
- [SQLite FTS5 Documentation](https://www.sqlite.org/fts5.html)
- [PEP 561 - Distributing and Packaging Type Information](https://peps.python.org/pep-0561/)

---

## Changelog

| Date | Change | Author |
|------|--------|--------|
| 2026-07-28 | Initial optimization plan created | Vibe Code |
