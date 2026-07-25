# Plan: Add High-Value Analytics Tools

**Date**: 2026-07-25
**Objective**: Implement 4 high-value MCP tools from `future-tool-ideas.md` that provide cost, usage, and model analytics using existing data in the `messages` table.

---

## Tools to Add

| Tool                | Purpose                               | Data Source                                       |
| ------------------- | ------------------------------------- | ------------------------------------------------- |
| `get_cost_estimate` | Calculate cost per session/project    | `model` + `tokens_input/output` in `messages`     |
| `get_usage_trends`  | Daily/weekly token/message aggregates | `timestamp` + `tokens_input/output` in `messages` |
| `get_model_usage`   | Breakdown by model per project        | `model` + `tokens_input/output` in `messages`     |
| `get_tool_usage`    | Tool frequency analysis per project   | `tool_names` JSON in `messages`                   |

---

## Implementation Steps

### Step 1: Model Pricing Data (`src/claude_history_mcp/utils.py`)

Add `MODEL_PRICING` dictionary mapping model IDs to per-million-token costs:

- Input: $3.00-$15.00 per 1M tokens (varies by model)
- Output: $15.00-$75.00 per 1M tokens (varies by model)
- Include fallback pricing for unknown models

### Step 2: Cache Aggregation Methods (`src/claude_history_mcp/cache.py`)

Add 4 new methods to `CacheManager`:

```python
def get_usage_trends(self, project_id: int | None, days: int = 30) -> list[dict]:
    """Aggregate tokens/messages by day."""
    # SQL: GROUP BY date(timestamp), SUM tokens, COUNT messages

def get_model_usage(self, project_id: int | None) -> list[dict]:
    """Breakdown by model: message count, tokens, cost."""
    # SQL: GROUP BY model, SUM tokens, COUNT messages

def get_tool_usage(self, project_id: int | None) -> list[dict]:
    """Tool frequency analysis."""
    # Python: Parse tool_names JSON, count occurrences

def get_error_counts(self, project_id: int | None, days: int = 30) -> list[dict]:
    """Error aggregation by day."""
    # SQL: WHERE is_error=1, GROUP BY date(timestamp)
```

### Step 3: Search Engine Methods (`src/claude_history_mcp/search.py`)

Add 4 new methods to `SearchEngine`:

```python
def get_cost_estimate(self, project: str | None, session_id: str | None) -> dict:
    """Calculate cost using MODEL_PRICING and token counts."""

def get_usage_trends(self, project: str | None, days: int = 30) -> list[dict]:
    """Return time-series data for messages/tokens."""

def get_model_usage(self, project: str | None) -> list[dict]:
    """Return model breakdown with costs."""

def get_tool_usage(self, project: str | None) -> list[dict]:
    """Return tool frequency list sorted by count."""
```

### Step 4: MCP Server Tools (`src/claude_history_mcp/server.py`)

Register the 4 new tools with:

- Full docstrings in Google style
- Type hints for all parameters
- Error handling with try/except returning `{"error": str(e)}`
- Optional parameters with sensible defaults

### Step 5: Tests

**Unit tests** (`tests/test_cache.py`):

- Test `get_usage_trends()` with mock data
- Test `get_model_usage()` with multiple models
- Test `get_tool_usage()` with JSON tool_names
- Test `get_error_counts()` with error entries

**Unit tests** (`tests/test_search.py`):

- Test `get_cost_estimate()` calculation accuracy
- Test `get_usage_trends()` date filtering
- Test `get_model_usage()` with unknown models (fallback pricing)
- Test `get_tool_usage()` with empty/malformed tool_names

**Integration tests** (`tests/test_server.py`):

- Verify all 4 tools are listed in `list_tools()`
- Test each tool via FastMCP client
- Verify error handling for invalid inputs

---

## File Changes

| File                               | Changes                                              |
| ---------------------------------- | ---------------------------------------------------- |
| `src/claude_history_mcp/utils.py`  | Add `MODEL_PRICING` dict + `calculate_cost()` helper |
| `src/claude_history_mcp/cache.py`  | Add 4 aggregation methods (~80 lines)                |
| `src/claude_history_mcp/search.py` | Add 4 analytics methods (~120 lines)                 |
| `src/claude_history_mcp/server.py` | Add 4 tool registrations (~80 lines)                 |
| `tests/test_cache.py`              | Add ~60 lines for aggregation tests                  |
| `tests/test_search.py`             | Add ~80 lines for analytics tests                    |
| `tests/test_server.py`             | Add ~40 lines for integration tests                  |

---

## Pricing Strategy

Use hardcoded pricing from Anthropic's published rates:

- Claude Opus 4: $15/$75 per 1M tokens (input/output)
- Claude Sonnet 4/5: $3/$15 per 1M tokens
- Claude Haiku 4/5: $0.25/$1.25 per 1M tokens
- Fallback: $3/$15 (Sonnet pricing) for unknown models

---

## Testing Strategy

1. **Isolated HOME**: All tests use `monkeypatch.setenv("HOME", ...)` - no real data
2. **In-memory SQLite**: Tests create fresh `CacheManager` instances per test
3. **Coverage**: Aim for 90%+ on new code paths
4. **Performance**: Aggregation queries should complete in <100ms for 10k messages

---

## Rollback Path

- All changes are additive (new methods, new tools)
- No existing functionality modified
- Can disable tools by removing `@mcp.tool` decorator if issues found
- SQLite schema unchanged (no migrations needed)

---

## Non-Goals (This Sprint)

- Real-time streaming analytics
- Export to external formats (CSV, JSON)
- Cost alerts/thresholds
- Dashboard/visualization integration
- Historical pricing changes (use current rates only)

---

## Acceptance Criteria

- [ ] All 4 tools pass unit tests
- [ ] All 4 tools pass integration tests via FastMCP client
- [ ] Cost calculations accurate to ±5% of manual calculation
- [ ] No regressions in existing 112 tests
- [ ] `pyright --strict` passes with 0 errors
- [ ] Documentation updated in CLAUDE.md (new tools section)

---

## Estimated Effort

- Step 1 (Pricing): 15 min
- Step 2 (Cache): 45 min
- Step 3 (Search): 60 min
- Step 4 (Server): 30 min
- Step 5 (Tests): 60 min
- **Total**: ~3.5 hours

---

## Next Steps After Approval

1. Write `MODEL_PRICING` to `utils.py`
2. Implement cache aggregation methods
3. Implement search engine methods
4. Register MCP tools
5. Write unit tests
6. Write integration tests
7. Run full test suite
8. Update CLAUDE.md documentation
