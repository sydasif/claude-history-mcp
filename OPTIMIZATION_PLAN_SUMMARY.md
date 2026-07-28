# Optimization Plan - Quick Reference

> **Full Plan:** See [OPTIMIZATION_PLAN.md](./OPTIMIZATION_PLAN.md)

---

## Priority Matrix

| Priority | Task | File | Effort | Impact |
|----------|------|------|--------|--------|
| 🔴 **High** | Add `py.typed` marker | `src/.../py.typed` | 5 min | ⭐⭐⭐ |
| 🔴 **High** | Consolidate dev dependencies | `pyproject.toml` | 5 min | ⭐⭐⭐ |
| 🔴 **High** | Session ID validation | `server.py` | 10 min | ⭐⭐⭐⭐ |
| 🔴 **High** | Batch insert optimization | `loader.py` | 10 min | ⭐⭐⭐⭐ |
| 🔴 **High** | FTS5 prefix indexing | `cache.py` | 2 min | ⭐⭐⭐ |
| 🟡 **Medium** | Connection pooling | `cache.py` | 30 min | ⭐⭐⭐ |
| 🟡 **Medium** | Add type hints | `cache.py` | 20 min | ⭐⭐ |
| 🟡 **Medium** | SQL query helpers | `cache.py` | 45 min | ⭐⭐ |
| 🟡 **Medium** | Performance benchmarks | `tests/test_perf.py` | 45 min | ⭐⭐ |
| 🟡 **Medium** | Integration tests | `tests/test_integration.py` | 30 min | ⭐⭐ |
| 🟡 **Medium** | CLI entry point | `cli.py` | 30 min | ⭐⭐ |
| 🟢 **Low** | Query caching | `search.py` | 30 min | ⭐⭐ |
| 🟢 **Low** | Rate limiting | `server.py` | 5 min | ⭐ |
| 🟢 **Low** | Enhanced health | `server.py` | 10 min | ⭐ |
| 🟢 **Low** | API documentation | `docs/api.yaml` | 45 min | ⭐ |

---

## Quick Start (1-2 hours)

### 1. Add `py.typed` marker
```bash
touch src/claude_history_mcp/py.typed
```

### 2. Consolidate dependencies in `pyproject.toml`
Remove `[project.optional-dependencies]` and keep only `[dependency-groups.dev]`.

### 3. Add session ID validation in `server.py`
```python
import re
SESSION_ID_PATTERN = re.compile(r'^[a-f0-9]{8,64}$')

# In list_session_transcript and list_session_stats:
if not SESSION_ID_PATTERN.match(session_id):
    return [{"error": "Invalid session_id format"}]
```

### 4. Optimize batch inserts in `loader.py`
Move batch insert to end of `load_jsonl_file()` function instead of inside the loop.

### 5. Enable FTS5 prefix indexing in `cache.py`
```python
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

---

## Files to Create

- [ ] `src/claude_history_mcp/py.typed` - PEP 561 marker
- [ ] `src/claude_history_mcp/cli.py` - CLI interface
- [ ] `tests/test_performance.py` - Performance benchmarks
- [ ] `tests/test_integration.py` - Integration tests
- [ ] `docs/api.yaml` - OpenAPI specification

---

## Files to Modify

- [ ] `pyproject.toml` - Consolidate dependencies, add py.typed to package-data
- [ ] `src/claude_history_mcp/server.py` - Add input validation, rate limiting, enhanced health
- [ ] `src/claude_history_mcp/loader.py` - Optimize batch inserts
- [ ] `src/claude_history_mcp/cache.py` - Add prefix indexing, connection pooling, type hints, SQL helpers
- [ ] `src/claude_history_mcp/search.py` - Add query caching
- [ ] `README.md` - Add examples section

---

## Commands to Verify

```bash
# Run tests
uv run pytest -v

# Check linting
uv run ruff check src/

# Check types
uv run mypy src/

# Run new performance tests (after creating)
uv run pytest tests/test_performance.py -v

# Test CLI (after creating)
uv run python -m claude_history_mcp.cli --help
```

---

## Expected Outcomes

| Optimization | Before | After | Improvement |
|--------------|--------|-------|-------------|
| Load time (10k msgs) | ~X sec | ~0.7X sec | 30-50% faster |
| Search time | ~Y ms | ~0.8Y ms | 20-25% faster |
| Cache size | ~Z MB | ~0.6Z MB | 40% smaller |
| Type safety | Good | Better | More IDE support |
| Maintainability | Good | Better | Easier to extend |

---

## Notes

- All current tests (118) pass ✅
- mypy strict mode passes ✅
- ruff linting passes ✅
- No breaking changes proposed
- All optimizations are backward compatible
