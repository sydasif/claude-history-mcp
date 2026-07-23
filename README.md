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
git clone https://github.com/sydasif/claude-history-mcp
cd claude-history-mcp
uv sync
```

### Install with pip

```bash
pip install -e .
```

### Add to Claude Code (user scope)

```bash
claude mcp add claude-history --scope user -- uvx --from git+https://github.com/sydasif/claude-history-mcp claude-history-mcp
```

This installs directly from GitHub via `uvx` — no PyPI publish needed. The `--scope user` flag makes the server available across all projects.

## Use Case Workflows

Each tool solves a specific class of problem. Here's how to use them, mapped to real questions:

| #   | You want to...                           | Use this tool                               | How                                                                                                                                                                      |
| --- | ---------------------------------------- | ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1   | **Browse everything you've worked on**   | `list_projects`                             | Returns all projects with session counts, token totals, and date ranges. Start here if you're exploring.                                                                 |
| 2   | **Find what you did recently**           | `get_recent_activity`                       | `get_recent_activity(hours=24)` or `(hours=72)` — shows the latest messages across all projects in the time window. Great for "what was I doing yesterday?"              |
| 3   | **Search for a specific topic or error** | `search_messages`                           | `search_messages(query="deploy script", project="my-project", role="user")` — full-text search with filters for project, role, tool name, and date.                      |
| 4   | **Pull a full conversation transcript**  | `get_session`                               | `get_session(session_id="a7431e9a-...")` — get the complete message history with timestamps, tool calls, and results. Use for review, export, or feeding to another LLM. |
| 5   | **Analyze session cost and tool usage**  | `get_session_stats`                         | `get_session_stats(session_id="a7431e9a-...")` — see token counts, tool-call breakdown, models used, errors, and duration.                                               |
| 6   | **Find past commands you typed**         | `search_history`                            | `search_history(query="docker build", from_date="3 days ago")` — searches the global history of every `!` command across all sessions.                                   |
| 7   | **Filter sessions by project or date**   | `list_sessions`                             | `list_sessions(project="my-project", from_date="last week")` — lists sessions with titles, summaries, timestamps, and token usage.                                       |
| 8   | **Check what tools Claude used most**    | `get_session_stats` + `get_recent_activity` | Stats roll up tool call counts per session. Combine with recent activity for a complete picture.                                                                         |
| 9   | **Count how many prompts you gave**      | `get_session` + role filter                 | Pull the transcript, then count entries with `entry_type == "user"`.                                                                                                     |

### Workflow Examples

#### Finding and Exporting a Past Session

```
list_sessions(project="my-project", from_date="yesterday")
# → pick a session_id from results

get_session(session_id="a7431e9a-48bb-44c9-b2cf-84121bf94917")
# → full transcript for review or export
```

#### Debugging What Went Wrong

```
get_recent_activity(hours=48)
# → see what you were working on

search_messages(query="error", project="my-project")
# → find errors across all conversations in that project

get_session(session_id="a7431e9a-...", include_thinking=False)
# → get the full context around the error
```

#### Understanding Usage Patterns

```
list_projects()
# → see all projects and total token consumption

get_session_stats(session_id="a7431e9a-...")
# → drill into a specific session: tools used, models, errors

list_sessions(from_date="last 7 days", limit=100)
# → view all sessions from the past week with stats
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

<!-- Edge case handling details are maintained in `.claude/CLAUDE.md` (Real-World Edge Cases) to keep a single source of truth. -->

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
