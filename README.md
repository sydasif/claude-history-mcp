# Claude History

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-brightgreen.svg)](https://www.python.org/downloads/)
[![GitHub stars](https://img.shields.io/github/stars/sydasif/claude-history-mcp?style=social)](https://github.com/sydasif/claude-history-mcp)

**Built-in memory search `MCP` for `Claude`** — search every conversation, every session, every project. Your complete development history, queryable in seconds.

> **How it works:** Claude Code stores conversation data in `~/.claude/projects/**/*.jsonl`. Claude History MCP parses these files, caches them in SQLite, and exposes tools so Claude can search your full development history on demand.

---

## Features

| Feature                    | Description                                                                                           |
| -------------------------- | ----------------------------------------------------------------------------------------------------- |
| **Full-text search**       | Search across all session messages, tool outputs, and history commands                                |
| **Natural language dates** | Filter by "yesterday", "last week", "March 2026" — powered by `dateparser`                            |
| **Incremental parsing**    | Only re-parses files that changed (mtime-based SQLite cache)                                          |
| **7 MCP tools**            | Search, list, filter, analyze — with pagination on all list/search tools                              |
| **Cost analytics**         | Estimate token costs, usage trends, and model breakdowns                                              |
| **Smart memory decay**     | Ebbinghaus forgetting curve with spaced-repetition — notes you recall survive, stale notes auto-evict |
| **Zero config**            | Points at your existing `~/.claude/` data — no setup, no API keys, no cloud                           |
| **Surrogate-safe**         | Handles real-world JSONL edge cases (missing timestamps, truncated tool names, surrogate characters)  |

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
| "Find sessions about payment processing"            | `search_messages`        | `search_messages(query="payment", role="user")`         |
| "Show me the session where I debugged the timeout"  | `get_session_transcript` | `get_session_transcript(session_id="abc123...")`        |
| "Search what I typed in the terminal"               | `search_history`         | `search_history(query="terraform apply")`               |
| "List my projects and recent sessions"              | `list_sessions`          | `list_sessions()`                                       |
| "Sessions in the auth project from last month"      | `list_sessions`          | `list_sessions(project="auth", from_date="last month")` |
| "What models am I using and how much do they cost?" | `get_model_usage`        | `get_model_usage()`                                     |
| "Save a new memory note"                            | `memory_retain`          | `memory_retain(project="auth", statement="...")`        |
| "Synthesize evidence for a query"                   | `memory_reflect`         | `memory_reflect(project="auth", query="...")`           |

All list/search tools support `offset` for cursor-based pagination.

---

## Smart Memory Decay (Ebbinghaus Forgetting Curve)

The `memory_retain` / `memory_reflect` tools now include an automatic decay engine
based on the **Ebbinghaus forgetting curve** with **spaced-repetition reinforcement**:

| Concept                | Behavior                                                                                      |
| ---------------------- | --------------------------------------------------------------------------------------------- |
| **Retention score**    | `R = e^(-elapsed_turns / stability)` — decays exponentially over time                         |
| **Recall boost**       | Each `memory_reflect` call recalls matching notes → `stability *= (1 + ln(1 + recall_count))` |
| **Eviction**           | Notes with `R < 0.20` are auto-pruned on next `memory_reflect`                                |
| **Foundational notes** | `note_type="decision"` or `"bug"` → `is_foundational=True` → **never evict**                  |

**Practical effect:**

- Store a decision (`note_type="decision"`) → persists forever
- Store a workaround (`note_type="observation"`) → auto-evicted if never recalled
- Frequently recalled notes get stronger retention (spaced-repetition effect)
- No manual cleanup needed — the engine handles it on every `reflect` call

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
