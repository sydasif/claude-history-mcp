# Claude History MCP

MCP server that lets Claude Code query its own session history — search messages, list sessions, retrieve transcripts, and analyze usage patterns across all your projects.

Reads from `~/.claude/projects/**/*.jsonl` (session transcripts) and `~/.claude/history.jsonl` (command history), caches them in a local SQLite database, and exposes the data through fast, filtered MCP tools.

## Features

- **📁 Project browsing** — List all Claude Code projects with session counts, date ranges, and token totals
- **💬 Message search** — Full-text search across all conversations with filters for project, session, role, tool, and date range
- **📜 Session transcripts** — Retrieve the full conversation of any session, including tool calls and results
- **📊 Session statistics** — Token usage, tool call breakdown, models used, error count, and duration per session
- **⌨️ Command history** — Search the global history of every command you've typed across all sessions
- **🕐 Recent activity** — See what you've been working on across all projects in the last N hours
- **⚡ Incremental caching** — SQLite-backed with mtime tracking; only reparses changed files on restart
- **🔧 Natural language dates** — Use phrases like "yesterday", "last week" for all date filters

## Prerequisites

- **Python 3.12+**
- **uv** (recommended) or `pip`
- Claude Code session data at `~/.claude/projects/` (created automatically by Claude Code)

## Setup

### Install with uv (recommended)

```bash
git clone <repo-url>
cd claude-history-mcp
uv sync
```

### Install with pip

```bash
pip install -e .
```

### Add to Claude Code

```bash
# Run directly (no install needed)
claude mcp add claude-history -- uvx claude-history-mcp

# Or if installed locally
claude mcp add claude-history -- python -m claude_history_mcp.server
```

## Usage

Once the server is running, Claude Code can use these tools:

### `list_projects`

List all projects with metadata. Returns project path, display name, session count, message count, earliest/latest timestamps, and total token usage.

### `list_sessions`

List sessions with optional date and project filters:

```
list_sessions(project="my-project", from_date="yesterday", limit=10)
```

Each session shows its AI-generated title, summary, first user message, message count, and token usage.

### `search_messages`

Full-text search across all conversations:

```
search_messages(query="deploy script", project="my-project", role="user", from_date="last week")
```

Supports filtering by project, session ID, role (user/assistant/system), tool name, and date range.

### `get_session`

Get the full conversation transcript for a session:

```
get_session(session_id="a7431e9a-48bb-44c9-b2cf-84121bf94917")
```

Accepts session ID prefixes of at least 8 characters. Returns all messages with timestamps, role, text content, and tool calls.

### `get_session_stats`

Analyze a session's token usage and tool distribution:

```
get_session_stats(session_id="a7431e9a-48bb-44c9-b2cf-84121bf94917")
```

Returns duration, token counts, a sorted tool usage breakdown, models used, and error count.

### `search_history`

Search the global command history:

```
search_history(query="docker build", from_date="3 days ago")
```

### `get_recent_activity`

See recent work across all projects:

```
get_recent_activity(hours=24)
```

### Available Resources

| Resource URI        | Description               |
| ------------------- | ------------------------- |
| `claude://projects` | Markdown list of projects |
| `claude://history`  | Recent command history    |

## Project Structure

```
claude-history-mcp/
├── pyproject.toml              # Project metadata, dependencies, build config
├── uv.lock                     # Locked dependency versions
├── .python-version             # Python 3.12
├── spec.md                     # Full developer specification
├── src/
│   └── claude_history_mcp/
│       ├── __init__.py         # Package init, cache path, initialize()
│       ├── server.py           # FastMCP server with tools & resources
│       ├── models.py           # Pydantic models for all transcript entry types
│       ├── parser.py           # JSONL entry dispatch, text extraction helpers
│       ├── cache.py            # SQLite cache layer (schema, CRUD, mtime tracking)
│       ├── discovery.py        # File/project discovery under ~/.claude/projects/
│       ├── loader.py           # JSONL parsing pipeline → cache insertion
│       ├── search.py           # Query engine — natural dates, filters, aggregation
│       └── utils.py            # Surrogate scrubbing, timestamp parsing, path helpers
└── tests/
    ├── test_parser.py          # Entry parsing, text extraction unit tests
    ├── test_server.py          # MCP tool/resource integration tests
    ├── test_cache.py
    ├── test_search.py
    ├── test_discovery.py
    ├── test_loader.py
    ├── test_models.py
    └── test_utils.py
```

## Module Overview

| Module         | Responsibility                                                                     |
| -------------- | ---------------------------------------------------------------------------------- |
| `models.py`    | Typed Pydantic models for user/assistant/system/summary entries and content blocks |
| `parser.py`    | Converts raw JSON dicts into typed models, extracts searchable text and tool names |
| `cache.py`     | SQLite database — stores projects, sessions, messages, and command history         |
| `discovery.py` | Scans `~/.claude/projects/` directories for JSONL session files                    |
| `loader.py`    | Reads JSONL files, parses entries, inserts into cache with mtime tracking          |
| `search.py`    | Higher-level query methods with natural-language date parsing and post-filtering   |
| `server.py`    | FastMCP server registering 7 tools and 2 resources                                 |
| `utils.py`     | Surrogate character scrubbing, timestamp parsing, path helpers                     |

## Edge Case Handling

The parser handles numerous real-world edge cases found in Claude Code session data:

- **Missing timestamps** (~21% of entries) — entries without timestamps always survive date filtering
- **Surrogate characters** (U+D800–U+DFFF) — scrubbed before SQLite storage
- **Dual session ID fields** — `sessionId` takes precedence, falls back to `session_id`
- **Corrupted tool names** — truncated MCP names stored as-is, no normalization
- **tool_result variants** — both `str` and `list[dict]` formats normalized to text
- **API error entries** — flagged `is_error=True`, included in search results
- **Unknown entry types** — with UUID retained as `BaseEntry`; without UUID skipped
- **Incremental loading** — only changed JSONL files are reparsed (mtime-based)

## Development

```bash
# Install dev dependencies
uv sync --group dev

# Run tests
uv run pytest

# Run with coverage
uv run pytest --cov=claude_history_mcp

# Clear and rebuild the cache
python -c "from claude_history_mcp import initialize; initialize(force=True)"
```

Tests use an isolated `HOME` directory — they never touch your real `~/.claude` data.

## Contributing

Contributions are welcome. Please follow these guidelines:

1. Open an issue first to discuss the change
2. Write tests for any new functionality
3. Ensure the full test suite passes
4. Update `spec.md` if the data model or tool interface changes

### Commit Style

Conventional commits: `feat(scope):`, `fix(scope):`, `refactor(scope):`, `test(scope):`, `chore(scope):`

## License

MIT
