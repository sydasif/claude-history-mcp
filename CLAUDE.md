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

- **discovery.py** — Scans `~/.claude/projects/` for directories containing JSONL files. Each directory is a "project" (encoded path like `-home-zulu-my-project`). Returns `ProjectInfo`/`SessionFileInfo` dataclasses.
- **loader.py** — Reads JSONL files line-by-line, delegates to parser, inserts results into cache. Tracks file mtimes so only changed files are reparsed. `load_history_file()` is called on every start (idempotent via INSERT OR IGNORE).
- **parser.py** — `create_entry()` dispatches raw JSON dicts to the right Pydantic model. `SILENT_SKIP_TYPES` silently drops 8 non-essential entry types. Unknown types with a `uuid` are retained as `BaseEntry`; without `uuid` they're dropped.
- **cache.py** — SQLite with WAL mode, threading lock. 5 tables: `projects`, `sessions`, `messages`, `history_commands`, `file_tracking`. `recompute_project_stats()` rolls up session aggregates to parent project.
- **search.py** — `SearchEngine` wraps `CacheManager` with natural-language date parsing (`dateparser`), prefix-based session-ID matching, and post-filtering for tool names and dates.
- **models.py** — Pydantic models: `ContentItem` discriminated union (text, tool_use, tool_result, thinking, image), `BaseEntry` with `resolved_session_id` property, typed entries per spec, `HistoryCommand`.
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

7 tools, 2 resources — all defined in `server.py` with try/except wrappers returning `{"error": str(e)}` on failure:

- `list_projects()` / `list_sessions()` / `search_messages()` / `get_session()` / `get_session_stats()` / `search_history()` / `get_recent_activity(hours=24, limit=100)`
- Resources: `claude://projects`, `claude://history`

Tools accept natural-language date strings ("yesterday", "last week") via `dateparser`.

### Real-World Edge Cases (from spec.md)

- ~21% of entries lack timestamps — these survive date filtering per spec 3.2
- `sessionId` vs `session_id` — prefer camelCase, fall back to snake_case
- MCP tool names can be truncated — store as-is, no normalization
- Tool result content is either `str` or `list[dict]` — normalize to text
- Lone surrogate characters (U+D800–U+DFFF) must be scrubbed before SQLite
- Unknown entry types with a `uuid` are kept for searchability

### Recent Fixes (2026-07-23)

1. **`get_recent_activity` limit parameter** — Added optional `limit` parameter (default 100) to prevent token overflow on large result sets. Default preserves backward compatibility.
2. **Timezone handling** — `parse_timestamp()` and `_parse_natural_date()` now return naive UTC datetimes for consistent comparison. Fixed "can't compare offset-naive and offset-aware" errors.

### Deployment

Not published to PyPI. Served via uvx from GitHub:

```bash
claude mcp add claude-history --scope user -- uvx --from git+https://github.com/sydasif/claude-history-mcp claude-history-mcp
```

The entry point name (`claude-history-mcp`) must match exactly — it's the `[project.scripts]` key in `pyproject.toml`.
