"""Claude History MCP Server — exposes session history as MCP tools."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from fastmcp import FastMCP

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
def list_projects() -> list[dict[str, Any]]:
    """List all Claude Code projects with session counts and date ranges.

    Returns project paths, display names, message counts, and timestamp ranges.
    """
    try:
        engine = _get_engine()
        return engine.list_projects()
    except Exception as e:
        return [{"error": str(e)}]


@mcp.tool
def list_sessions(
    project: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List Claude Code sessions with summaries, timestamps, and token usage.

    Args:
        project: Filter by project path or name (partial match, case-insensitive)
        from_date: Filter sessions after this date (natural language: "yesterday", "last week")
        to_date: Filter sessions before this date
        limit: Maximum sessions to return (default 50)
    """
    try:
        engine = _get_engine()
        return engine.list_sessions(
            project=project, from_date=from_date, to_date=to_date, limit=limit
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
        )
    except Exception as e:
        return [{"error": str(e)}]


@mcp.tool
def get_session(
    session_id: str,
    include_thinking: bool = False,
) -> dict[str, Any]:
    """Get full conversation transcript for a session.

    Returns the complete message history including user prompts,
    assistant responses, tool calls, and tool results.

    Args:
        session_id: Session ID (full or prefix, minimum 8 characters)
        include_thinking: Whether to include thinking blocks (default false)
    """
    try:
        if len(session_id) < 8:
            return {"error": "session_id must be at least 8 characters"}
        engine = _get_engine()
        result = engine.get_session(session_id)
        if result is None:
            return {"error": f"Session not found: {session_id}"}
        # Handle ambiguous prefix match
        if isinstance(result, dict) and result.get("error") == "ambiguous_prefix":
            candidates = result["candidates"]
            return {
                "error": f"Multiple sessions match prefix '{session_id}'. Use more characters:",
                "candidates": candidates,
            }
        # Filter thinking blocks if requested
        if not include_thinking and "messages" in result:
            for msg in result["messages"]:
                if msg.get("entry_type") == "assistant":
                    try:
                        raw = json.loads(msg["raw_json"])
                        content = raw.get("message", {}).get("content", [])
                        filtered = [c for c in content if c.get("type") != "thinking"]
                        raw["message"]["content"] = filtered
                        msg["raw_json"] = json.dumps(raw, ensure_ascii=False)
                    except Exception:
                        logger.exception("Failed to filter thinking blocks")
        return result
    except Exception as e:
        return {"error": str(e)}


@mcp.tool
def get_session_stats(session_id: str) -> dict[str, Any]:
    """Get token usage, tool call counts, and duration for a session.

    Args:
        session_id: Session ID (full or prefix, minimum 8 characters)
    """
    try:
        if len(session_id) < 8:
            return {"error": "session_id must be at least 8 characters"}
        engine = _get_engine()
        result = engine.get_session_stats(session_id)
        if result is None:
            return {"error": f"Session not found: {session_id}"}
        return result
    except Exception as e:
        return {"error": str(e)}


@mcp.tool
def search_history(
    query: str,
    project: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 50,
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
    """
    try:
        engine = _get_engine()
        return engine.search_history(
            query=query,
            project=project,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
        )
    except Exception as e:
        return [{"error": str(e)}]


@mcp.tool
def get_recent_activity(hours: int = 24, limit: int = 100) -> list[dict[str, Any]]:
    """Get recent Claude Code activity across all projects.

    Shows the most recent messages (user prompts and assistant responses)
    from the specified time window.

    Args:
        hours: Look back this many hours (default 24)
        limit: Maximum results to return (default 100)
    """
    try:
        engine = _get_engine()
        return engine.get_recent_activity(hours=hours, limit=limit)
    except Exception as e:
        return [{"error": str(e)}]


@mcp.resource("claude://projects")
def get_projects_resource() -> str:
    """List of all Claude Code projects."""
    engine = _get_engine()
    projects = engine.list_projects()
    if not projects:
        return "No Claude Code projects found."
    lines = ["# Claude Code Projects\n"]
    for p in projects:
        lines.append(f"- **{p.get('display_name', p.get('project_path', 'unknown'))}**")
        lines.append(f"  Path: `{p.get('project_path', '')}`")
        lines.append(f"  Messages: {p.get('total_messages', 0)}")
        lines.append(
            f"  Tokens: {p.get('total_input_tokens', 0)} in / {p.get('total_output_tokens', 0)} out"
        )
    return "\n".join(lines)


@mcp.resource("claude://history")
def get_history_resource() -> str:
    """Recent command history."""
    engine = _get_engine()
    commands = engine.search_history(query="", limit=20)
    if not commands:
        return "No command history found."
    lines = ["# Recent Claude Code Commands\n"]
    for cmd in commands:
        lines.append(f"- `{cmd.get('display', '')}` ({cmd.get('project', 'unknown')})")
    return "\n".join(lines)


def main() -> None:
    """Entry point for the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
