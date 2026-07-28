# Claude History

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-brightgreen.svg)](https://www.python.org/downloads/)
[![GitHub stars](https://img.shields.io/github/stars/sydasif/claude-history-mcp?style=social)](https://github.com/sydasif/claude-history-mcp)

**Built-in memory search `MCP` for `Claude`** — search every conversation, every session, every project. Your complete development history, queryable in seconds.

> **How it works:** Claude Code stores conversation data in `~/.claude/projects/**/*.jsonl`. Claude History MCP parses these files, caches them in SQLite, and exposes tools so Claude can search your full development history on demand.

---

## Features

| Feature                    | Description                                                                                          |
| -------------------------- | ---------------------------------------------------------------------------------------------------- |
| **Full-text search**       | Search across all session messages, tool outputs, and history commands                               |
| **Natural language dates** | Filter by "yesterday", "last week", "March 2026" — powered by `dateparser`                           |
| **Incremental parsing**    | Only re-parses files that changed (mtime-based SQLite cache)                                         |
| **10 MCP tools**           | Search, list, filter, analyze — with pagination on all list/search tools                             |
| **Cost analytics**         | Estimate token costs, usage trends, model breakdowns, and tool frequency                             |
| **Session hierarchy**      | Tree view: projects → sessions → messages with glob pattern search                                   |
| **Zero config**            | Points at your existing `~/.claude/` data — no setup, no API keys, no cloud                          |
| **Surrogate-safe**         | Handles real-world JSONL edge cases (missing timestamps, truncated tool names, surrogate characters) |

---

## Quick Start

**Prerequisites:** Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/) installed.

```bash
# Add to Claude Code (user scope — available in ALL projects)
claude mcp add claude-history --scope user -- uvx --from git+https://github.com/sydasif/claude-history-mcp claude-history-mcp
```

**That's it.** Next time you open Claude Code, you have a searchable memory.

---

## What You Can Ask

| Question                                            | Tool                     | Example                                                 |
| --------------------------------------------------- | ------------------------ | ------------------------------------------------------- |
| "What did I work on last week?"                     | `list_recent_activity`   | `list_recent_activity(hours=168)`                       |
| "Find sessions about payment processing"            | `search_messages`        | `search_messages(query="payment", role="user")`         |
| "Show me the session where I debugged the timeout"  | `get_session_transcript` | `get_session_transcript(session_id="abc123...")`        |
| "How many tokens did that refactoring cost?"        | `get_session_stats`      | `get_session_stats(session_id="abc123...")`             |
| "What commands did I run to deploy?"                | `search_history`         | `search_history(query="terraform apply")`               |
| "List all my projects and their activity"           | `list_sessions`          | `list_sessions()`                                       |
| "Sessions in the auth project from last month"      | `list_sessions`          | `list_sessions(project="auth", from_date="last month")` |
| "What models am I using and how much do they cost?" | `get_model_usage`        | `get_model_usage()`                                     |
| "Which tools do I use most frequently?"             | `get_tool_usage`         | `get_tool_usage()`                                      |
| "Show me the project hierarchy tree"                | `get_project_tree`       | `get_project_tree(project="auth")`                      |
| "Get aggregated stats for a project"                | `get_project_stats`      | `get_project_stats(project="auth")`                     |

All list/search tools support `offset` for cursor-based pagination.

---

## Architecture

```text
~/.claude/projects/**/*.jsonl  ──┐
~/.claude/history.jsonl        ──┤
                                  ▼
┌──────────────────────────────────────────────────────┐
│           claude-history-mcp (MCP Server)            │
│  ┌─────────────┐  ┌────────────┐  ┌───────────────┐  │
│  │   Tools     │  │ Resources  │  │  SearchEngine │  │
│  │ (search,    │  │ (projects, │  │ (full-text,   │  │
│  │  list,      │  │  history)  │  │  filters,     │  │
│  │  get, stats)│  │            │  │  aggregation) │  │
│  └──────┬──────┘  └─────┬──────┘  └───────┬───────┘  │
│         │               │                  │         │
│  ┌──────┴───────────────┴──────────────────┴───────┐ │
│  │              SQLite Cache Layer                 │ │
│  │  projects │ sessions │ messages │ history       │ │
│  └─────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

---

## Development

```bash
# Install dev dependencies
uv sync --group dev

# Run tests (isolated HOME — never touches real ~/.claude)
uv run pytest -v

# Run with coverage
uv run pytest --cov=claude_history_mcp

# Clear and rebuild cache
python -c "from claude_history_mcp import initialize; initialize(force=True)"
```

---

## Contributing

1. Fork the repo
2. Create a branch: `git checkout -b feature/your-feature`
3. Install dev dependencies: `uv sync --group dev`
4. Run tests: `uv run pytest -v`
5. Submit PR with a description of your change

---

## License

MIT
