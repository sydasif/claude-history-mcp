# Claude History MCP

**Built-in memory for Claude Code** — search every conversation, every session, every project. Your complete development history, queryable in seconds.

---

## The Problem

Claude Code remembers nothing between sessions. Every time you start fresh, you lose context:

- What did I work on last week?
- Which session had that debugging session for the payment bug?
- What commands did I run to deploy the staging environment?
- How many tokens did that refactoring session consume?

You have the data (`~/.claude/projects/**/*.jsonl`, `~/.claude/history.jsonl`) — but no way to query it.

## The Solution

**Claude History MCP** gives Claude Code a persistent, searchable memory across all your sessions and projects.

```
┌─────────────────────────────────────────────────────────────────┐
│  Your Query                                                    │
│  "What did I do on the payment refactor last Tuesday?"         │
└─────────────────────┬───────────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│  claude-history-mcp (MCP Server)                               │
│  • Parses ~/.claude/projects/**/*.jsonl + history.jsonl        │
│  • SQLite cache with incremental mtime-based invalidation      │
│  • Full-text search + natural language date filtering          │
└─────────────────────┬───────────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│  Results in Seconds                                            │
│  • Session with the payment refactor                           │
│  • Commands you ran (docker build, terraform apply, etc.)      │
│  • Token usage, tools used, errors encountered                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## What You Can Ask

| Question                                            | Tool                  | Example                                                               |
| --------------------------------------------------- | --------------------- | --------------------------------------------------------------------- |
| "What did I work on last week?"                     | `get_recent_activity` | `get_recent_activity(hours=168)`                                      |
| "Find sessions about payment processing"            | `search_messages`     | `search_messages(query="payment", role="user")`                       |
| "Show me the session where I debugged the timeout"  | `get_session`         | `get_session(session_id="abc123...")`                                 |
| "How many tokens did that refactoring cost?"        | `get_session_stats`   | `get_session_stats(session_id="abc123...")`                           |
| "What commands did I run to deploy?"                | `search_history`      | `search_history(query="terraform apply")`                             |
| "List all my projects and their activity"           | `list_projects`       | `list_projects()`                                                     |
| "Sessions in the auth project from last month"      | `list_sessions`       | `list_sessions(project="auth", from_date="last month")`               |
| "What is my estimated token cost?"                  | `get_cost_estimate`   | `get_cost_estimate(project="auth")`                                   |
| "Show daily usage trends for the past week"         | `get_usage_trends`    | `get_usage_trends(days=7)`                                            |
| "What models am I using and how much do they cost?" | `get_model_usage`     | `get_model_usage()`                                                   |
| "Which tools do I use most frequently?"             | `get_tool_usage`      | `get_tool_usage()`                                                    |
| "Skip to page 3 of results"                         | _all list/search_     | `list_sessions(limit=10, offset=20)` (supported on every list/search) |

---

## Under the Hood

| Component                   | Purpose                                                                                                                                                     |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **claude-code-log library** | Robust parsing of real-world JSONL (surrogate chars, missing timestamps, dual sessionId/session_id, truncated tool names, tool_result variants, API errors) |
| **SQLite cache**            | Incremental mtime-based invalidation — only reparses changed files                                                                                          |
| **Full-text search**        | SQLite `LIKE` on extracted content_text + natural language date parsing (`dateparser`)                                                                      |
| **FastMCP server**          | 7 tools + 2 resources exposed via stdio transport                                                                                                           |

---

## Quick Start

```bash
# Install
git clone https://github.com/sydasif/claude-history-mcp
cd claude-history-mcp
uv sync

# Add to Claude Code (user scope — available in ALL projects)
claude mcp add claude-history --scope user -- uvx --from git+https://github.com/sydasif/claude-history-mcp claude-history-mcp
```

**That's it.** Next time you open Claude Code, you have a searchable memory.

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

# Run tests (112 tests, isolated HOME — never touches real ~/.claude)
uv run pytest -v

# Run with coverage
uv run pytest --cov=claude_history_mcp

# Clear and rebuild cache
python -c "from claude_history_mcp import initialize; initialize(force=True)"
```

---

## License

MIT
