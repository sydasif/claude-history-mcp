# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync                        # Install all dependencies (include dev)
uv run pytest -v               # Run all tests
uv run pytest tests/test_server.py -v  # Single test file
uv run pytest -k "test_name"   # Single test by name
uv run pytest --cov=claude_history_mcp  # With coverage
uv run python -m claude_history_mcp.server  # Run the MCP server directly
```

## Architecture

### Data Flow

```
~/.claude/projects/**/*.jsonl  ─┐
~/.claude/history.jsonl        ─┤── discovery → loader → parser → SQLite cache → SearchEngine → FastMCP tools
```

- **Local JSONL parser** — Handles all real-world edge cases (surrogates, missing timestamps, dual sessionId/session_id, truncated tool names, tool_result variants, API errors, etc.)
- **discovery.py** — Scans `~/.claude/projects/` for directories containing JSONL files. Each directory is a "project" (encoded path like `-home-zulu-my-project`). Returns `ProjectInfo`/`SessionFileInfo` dataclasses.
- **loader.py** — Reads JSONL files line-by-line, delegates to library parser, inserts results into our cache. Tracks file mtimes so only changed files are reparsed. `load_history_file()` called on every start (idempotent via INSERT OR IGNORE).
- **parser.py** — Typed Pydantic models for transcript entries + JSONL parsing logic. `create_entry()` for JSONL → typed model, re-exports `parse_timestamp` from utils.
- **cache.py** — SQLite with WAL mode, threading lock. 5 tables: `projects`, `sessions`, `messages`, `history_commands`, `file_tracking`. `recompute_project_stats()` rolls up session aggregates to parent project.
- **search.py** — `SearchEngine` wraps `CacheManager` with natural-language date parsing (`dateparser`), prefix-based session-ID matching, and post-filtering for tool names and dates.
- **models.py** — Re-exports library types (`TranscriptEntry`, `UserTranscriptEntry`, etc.) + MCP-specific response models (`SessionSummary`, `ProjectInfo`, `MessageResult`, etc.)
- **utils.py** — `scrub_surrogates()` handles lone U+D800–U+DFFF characters, `parse_timestamp()` handles ISO 8601 with/without Z suffix, path helpers.

### Module Dependencies

```
server.py → __init__.py → cache.py, loader.py, search.py, utils.py
loader.py → discovery.py, parser.py, cache.py, models.py
parser.py → models.py, utils.py
search.py → cache.py, utils.py
```

### Entry Point

Defined in `pyproject.toml` as `claude-history-mcp` (dashes): calls `claude_history_mcp.server:main()` which runs `mcp.run()` (FastMCP stdio server).

### MCP Tools & Resources

10 tools, 2 resources — all defined in `server.py` with try/except wrappers returning `{"error": str(e)}` on failure:

- `list_sessions`, `search_messages`, `get_session`, `get_session_stats`, `search_history`, `get_recent_activity`, `get_model_usage(include_totals?, session_id?)`, `get_tool_usage`, `get_project_tree`, `get_project_stats(detail_level="basic|full")`
- Resources: `claude://projects`, `claude://history`

Tools accept natural-language date strings ("yesterday", "last week") via `dateparser`.
All list/search tools support `offset` parameter for cursor-based pagination.

### Real-World Edge Cases (handled by local parser)

- ~21% of entries lack timestamps — these survive date filtering per spec 3.2
- `sessionId` vs `session_id` — prefer camelCase, fall back to snake_case
- MCP tool names can be truncated — store as-is, no normalization
- Tool result content is either `str` or `list[dict]` — normalize to text
- Lone surrogate characters (U+D800–U+DFFF) must be scrubbed before SQLite
- Unknown entry types with a `uuid` are kept for searchability

### Recent Fixes (2026-07-24)

1. **Library dependency** — Removed `claude-code-log` dependency; parsing is now handled by local Pydantic models and parser to eliminate 20+ transitive dependencies.
2. **`get_recent_activity` limit parameter** — Added optional `limit` parameter (default 100) to prevent token overflow on large result sets
3. **Timezone handling** — `parse_timestamp()` and `_parse_natural_date()` return naive UTC datetimes for consistent comparison
4. **Silent skip types expanded** — Added `file-history-delta`, `pr-link` to skip list

### Deployment

Not published to PyPI. Served via uvx from GitHub:

```bash
claude mcp add claude-history --scope user -- uvx --from git+https://github.com/sydasif/claude-history-mcp claude-history-mcp
```

The entry point name (`claude-history-mcp`) must match exactly — it's the `[project.scripts]` key in `pyproject.toml`.

### Recent Fixes (2026-07-25)

1. **Pagination (offset)** — All list/search tools (`list_sessions`, `search_messages`, `search_history`, `get_recent_activity`) now support `offset` parameter for cursor-based pagination
2. **Prefix matching in get_session_stats** — `get_session_stats` now resolves session ID prefixes (min 8 chars), matching `get_session` behavior
3. **Type safety** — Resolved all 59 pyright static analysis errors across source and tests; now runs at 0 errors, 0 warnings
