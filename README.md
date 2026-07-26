# Claude History MCP

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-brightgreen.svg)](https://www.python.org/downloads/)
[![GitHub stars](https://img.shields.io/github/stars/sydasif/claude-history-mcp?style=social)](https://github.com/sydasif/claude-history-mcp)

**Built-in memory for Claude Code** — search every conversation, every session, every project. Your complete development history, queryable in seconds.

> **How it works:** Claude Code stores conversation data in `~/.claude/projects/**/*.jsonl`. Claude History MCP parses these files, caches them in SQLite, and exposes 11 MCP tools so Claude can search your full development history on demand.

---

## Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
- [What You Can Ask](#what-you-can-ask)
- [Under the Hood](#under-the-hood)
- [Architecture](#architecture)
- [Development](#development)
- [FAQ](#faq)
- [Contributing](#contributing)
- [License](#license)

---

## Features

| Feature                    | Description                                                                                          |
| -------------------------- | ---------------------------------------------------------------------------------------------------- |
| **Full-text search**       | Search across all session messages, tool outputs, and history commands                               |
| **Natural language dates** | Filter by "yesterday", "last week", "March 2026" — powered by `dateparser`                           |
| **Incremental parsing**    | Only reparses files that changed (mtime-based SQLite cache)                                          |
| **11 MCP tools**           | Search, list, filter, and analyze sessions — with pagination on all list/search tools                |
| **Cost analytics**         | Estimate token costs, usage trends, model breakdowns, and tool frequency                             |
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

<details>
<summary><strong>Or install from source</strong></summary>

```bash
git clone https://github.com/sydasif/claude-history-mcp
cd claude-history-mcp
uv sync

# Add to Claude Code
claude mcp add claude-history --scope user -- uvx --from git+https://github.com/sydasif/claude-history-mcp claude-history-mcp
```

</details>

---

## What You Can Ask

| Question                                            | Tool                  | Example                                                 |
| --------------------------------------------------- | --------------------- | ------------------------------------------------------- |
| "What did I work on last week?"                     | `get_recent_activity` | `get_recent_activity(hours=168)`                        |
| "Find sessions about payment processing"            | `search_messages`     | `search_messages(query="payment", role="user")`         |
| "Show me the session where I debugged the timeout"  | `get_session`         | `get_session(session_id="abc123...")`                   |
| "How many tokens did that refactoring cost?"        | `get_session_stats`   | `get_session_stats(session_id="abc123...")`             |
| "What commands did I run to deploy?"                | `search_history`      | `search_history(query="terraform apply")`               |
| "List all my projects and their activity"           | `list_projects`       | `list_projects()`                                       |
| "Sessions in the auth project from last month"      | `list_sessions`       | `list_sessions(project="auth", from_date="last month")` |
| "What is my estimated token cost?"                  | `get_cost_estimate`   | `get_cost_estimate(project="auth")`                     |
| "Show daily usage trends for the past week"         | `get_usage_trends`    | `get_usage_trends(days=7)`                              |
| "What models am I using and how much do they cost?" | `get_model_usage`     | `get_model_usage()`                                     |
| "Which tools do I use most frequently?"             | `get_tool_usage`      | `get_tool_usage()`                                      |

All list/search tools support `offset` for cursor-based pagination.

---

## Under the Hood

| Component          | Purpose                                                                                                                                  |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------- |
| **JSONL parser**   | Handles real-world edge cases: surrogate characters, missing timestamps, dual `sessionId`/`session_id`, truncated tool names, API errors |
| **SQLite cache**   | Incremental mtime-based invalidation — only reparses changed files                                                                       |
| **SearchEngine**   | Full-text search + natural language date parsing (`dateparser`) + prefix-based session ID matching                                       |
| **FastMCP server** | 11 tools + 2 resources exposed via stdio transport                                                                                       |

---

## Architecture

```
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
│         │               │                  │           │
│  ┌──────┴───────────────┴──────────────────┴───────┐  │
│  │              SQLite Cache Layer                 │  │
│  │  projects │ sessions │ messages │ history       │  │
│  └─────────────────────────────────────────────────┘  │
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

## FAQ

**Does this access or send my Claude conversations anywhere?**
No. It reads files from your local `~/.claude/` directory and caches them in a local SQLite database. Nothing is sent externally.

**What data does it store?**
A SQLite cache file in the project directory. It mirrors your `~/.claude/` JSONL files for fast querying. You can delete it at any time — it rebuilds on next startup.

**Can I use this without Claude Code?**
No. It's an MCP server designed to be used with Claude Code. It gives Claude Code the ability to search your own conversation history.

**The cache seems stale — how do I force a rebuild?**

```bash
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
