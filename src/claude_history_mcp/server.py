"""Claude History MCP Server -- exposes session history as MCP tools."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from fastmcp import FastMCP

from .memory import reflect, retain

_SESSION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{8,128}$")

if TYPE_CHECKING:
    from .search import SearchEngine

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "Claude History",
    instructions="Query Claude Code session history, search messages, and analyze usage patterns.",
)

# Global search engine, initialized on first tool call
_engine: SearchEngine | None = None


def _get_engine() -> SearchEngine:
    global _engine
    if _engine is None:
        from . import initialize

        _engine = initialize()
    return _engine


@mcp.tool
def list_sessions(
    project: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List Claude Code sessions with summaries, timestamps, and token usage.

    Args:
        project: Filter by project path or name (partial match, case-insensitive)
        from_date: Filter sessions after this date (natural language: "yesterday", "last week")
        to_date: Filter sessions before this date
        limit: Maximum sessions to return (default 50)
        offset: Number of sessions to skip for pagination (default 0)
    """
    try:
        engine = _get_engine()
        return engine.list_sessions(
            project=project,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        return [{"error": str(e)}]


@mcp.tool
def get_session_transcript(
    session_id: str,
    include_thinking: bool = False,
) -> list[dict[str, Any]]:
    """Get full conversation transcript for a session.

    Returns the complete message history including user prompts,
    assistant responses, tool calls, and tool results.

    Args:
        session_id: Session ID (full or prefix, minimum 8 characters)
        include_thinking: Whether to include thinking blocks (default false)
    """
    try:
        if len(session_id) < 8:
            return [{"error": "session_id must be at least 8 characters"}]
        if not _SESSION_ID_PATTERN.match(session_id):
            return [{"error": "Invalid session_id format"}]
        engine = _get_engine()
        result = engine.get_session(session_id)
        if result is None:
            return [{"error": f"Session not found: {session_id}"}]
        # Handle ambiguous prefix match
        if isinstance(result, dict) and result.get("error") == "ambiguous_prefix":
            candidates = result["candidates"]
            return [
                {
                    "error": f"Multiple sessions match prefix '{session_id}'. Use more characters:",
                    "candidates": candidates,
                }
            ]
        return [result]
    except Exception as e:
        return [{"error": str(e)}]


@mcp.tool
def search_history(
    query: str,
    project: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Search Claude Code command history (what you typed).

    Searches the global history.jsonl file containing all commands
    entered across all sessions.

    Args:
        query: Search term (case-insensitive)
        project: Filter by project path
        from_date: Filter after this date
        to_date: Filter before this date
        limit: Maximum results (default 50)
        offset: Number of results to skip for pagination (default 0)
    """
    try:
        engine = _get_engine()
        return engine.search_history(
            query=query,
            project=project,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        return [{"error": str(e)}]


@mcp.tool
def search_messages(
    query: str,
    project: str | None = None,
    session_id: str | None = None,
    role: str | None = None,
    tool_name: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Search messages across all Claude Code sessions.

    Full-text search across user prompts, assistant responses, tool outputs,
    and system messages. Returns matching messages with context.

    Args:
        query: Search term (case-insensitive substring match)
        project: Filter by project path or name
        session_id: Filter by specific session ID
        role: Filter by role: "user", "assistant", or "system"
        tool_name: Filter by tool name used (e.g., "Bash", "Edit", "Read")
        from_date: Filter messages after this date
        to_date: Filter messages before this date
        limit: Maximum results (default 50)
        offset: Number of results to skip for pagination (default 0)
    """
    try:
        engine = _get_engine()
        return engine.search_messages(
            query=query,
            project=project,
            session_id=session_id,
            role=role,
            tool_name=tool_name,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        return [{"error": str(e)}]


@mcp.tool
def get_model_usage(
    project: str | None = None,
    include_totals: bool = False,
    session_id: str | None = None,
) -> list[dict[str, Any]]:
    """Get usage breakdown grouped by model with estimated costs.

    Args:
        project: Filter by project path or name
        include_totals: Whether to include total cost/tokens
        session_id: Filter by specific session ID
    """
    try:
        engine = _get_engine()
        result = engine.get_model_usage(
            project=project, include_totals=include_totals, session_id=session_id
        )
        if isinstance(result, dict):
            return [result]
        return result
    except Exception as e:
        return [{"error": str(e)}]


@mcp.tool
def memory_retain(
    project: str,
    statement: str,
    description: str = "",
    session_ids: list[str] | None = None,
    note_type: str = "observation",
    related: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Store a new memory note grounded in specific sessions.

    Writes a markdown note to the project's memory/ directory with YAML
    frontmatter, cites source sessions, and updates MEMORY.md index.

    Args:
        project: Project display name or path fragment.
        statement: The natural language fact/decision/insight to remember.
        description: One-line summary for the memory index. Defaults to first 120 chars.
        session_ids: Session UUIDs that support this statement.
        note_type: observation | world | experience | decision | bug.
        related: Optional list of related note names or [[wikilink]] refs.
    """
    return retain(project, statement, description, session_ids, note_type, related)


@mcp.tool
def memory_reflect(
    project: str,
    query: str,
    note_names: list[str] | None = None,
    session_ids: list[str] | None = None,
    session_limit: int = 5,
) -> list[dict[str, Any]]:
    """Gather structured evidence for synthesis.

    Returns an evidence bundle combining memory notes and JSONL turns.
    Claude Code reasons over this bundle to produce a sourced answer.

    Args:
        project: Project display name or path fragment.
        query: The question to gather evidence for.
        note_names: Specific memory notes to include. None = all notes.
        session_ids: Specific sessions to pull verbatim evidence from.
        session_limit: Max sessions when session_ids is None.
    """
    return reflect(
        project=project,
        query=query,
        note_names=note_names,
        session_ids=session_ids,
        session_limit=session_limit,
    )


@mcp.resource("claude://health")
def get_health_resource() -> str:
    """Cache health and statistics for debugging."""
    try:
        engine = _get_engine()
        stats = engine.cache.get_stats()
        return (
            "# Claude History MCP Health\n\n"
            f"- Projects: {stats['projects']}\n"
            f"- Sessions: {stats['sessions']}\n"
            f"- Messages: {stats['messages']}\n"
            f"- History Commands: {stats['history_commands']}\n"
            f"- FTS5: {'Enabled' if getattr(engine.cache, '_fts_available', False) else 'Disabled (LIKE fallback)'}"
        )
    except Exception as e:
        return f"Health check failed: {e}"


def main() -> None:
    """Entry point for the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
