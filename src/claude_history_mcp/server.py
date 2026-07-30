"""Claude History MCP Server -- exposes session history as MCP tools."""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

from fastmcp import FastMCP

from .memory import reflect, retain

from .engine import get_engine as _get_engine

_SESSION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{8,128}$")

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "Claude History",
    instructions="Query Claude Code session history, search messages, and analyze usage patterns.",
)


def _validate_session_id(session_id: str) -> str | None:
    """Validate session_id format. Returns error message or None if valid."""
    if len(session_id) < 8:
        return "session_id must be at least 8 characters"
    if not _SESSION_ID_PATTERN.match(session_id):
        return "Invalid session_id format"
    return None


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
        if err := _validate_session_id(session_id):
            return [{"error": err}]
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


@mcp.tool
def get_file_changes(session_id: str) -> dict[str, Any]:
    """Get all file modifications in a session, grouped by file path.

    Returns which files were Read, Written, Edited, or executed via Bash,
    with timestamps and operation details.

    Args:
        session_id: Session ID (full or prefix, minimum 8 characters)
    """
    try:
        if err := _validate_session_id(session_id):
            return {"error": err}

        engine = _get_engine()
        messages = engine.cache.get_messages_by_tool(session_id)

        files: dict[str, list[dict[str, Any]]] = {}
        summary = {
            "reads": 0,
            "writes": 0,
            "edits": 0,
            "bash_commands": 0,
            "other_tools": 0,
        }

        for msg in messages:
            tool_names = (
                json.loads(msg.get("tool_names", "[]")) if msg.get("tool_names") else []
            )
            tool_inputs = (
                json.loads(msg.get("tool_inputs", "[]"))
                if msg.get("tool_inputs")
                else []
            )
            timestamp = msg.get("timestamp", "")

            for ti in tool_inputs:
                tool_name = ti.get("name", "")
                tool_input = ti.get("input", {})
                file_path = None

                if tool_name in ("Read", "Write", "Edit"):
                    file_path = tool_input.get("file_path")
                elif tool_name == "Bash":
                    file_path = f"[bash] {tool_input.get('command', '')[:100]}"
                    summary["bash_commands"] += 1
                elif tool_name == "Grep":
                    file_path = tool_input.get("path", ".")
                elif tool_name == "LSP":
                    file_path = tool_input.get("filePath")

                if file_path:
                    if file_path not in files:
                        files[file_path] = []

                    op = {"tool": tool_name, "timestamp": timestamp}

                    if tool_name == "Write":
                        content = tool_input.get("content", "")
                        op["size"] = len(content)
                        summary["writes"] += 1
                    elif tool_name == "Edit":
                        op["old_string"] = tool_input.get("old_string", "")[:100]
                        op["new_string"] = tool_input.get("new_string", "")[:100]
                        summary["edits"] += 1
                    elif tool_name == "Read":
                        summary["reads"] += 1
                    elif tool_name == "Bash":
                        summary["bash_commands"] += 1
                    else:
                        summary["other_tools"] += 1

                    files[file_path].append(op)

        return {
            "session_id": session_id,
            "files": files,
            "summary": {
                "files_modified": len(files),
                **summary,
            },
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool
def search_file_changes(
    file_path: str,
    project: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Find all sessions that modified a specific file.

    Args:
        file_path: File path to search for (partial match)
        project: Filter by project path or name (optional)
        limit: Maximum results to return (default 50)
    """
    try:
        engine = _get_engine()
        project_id = None
        if project:
            projects = engine.cache.get_all_projects()
            for p in projects:
                if (
                    project.lower() in p["project_path"].lower()
                    or project.lower() in (p.get("display_name") or "").lower()
                ):
                    project_id = p["id"]
                    break

        messages = engine.cache.search_tool_inputs(file_path, project_id)

        sessions: dict[str, dict[str, Any]] = {}
        for msg in messages[:limit]:
            sid = msg.get("session_id", "")
            if sid not in sessions:
                sessions[sid] = {
                    "session_id": sid,
                    "project": msg.get("display_name", ""),
                    "project_path": msg.get("project_path", ""),
                    "operations": [],
                }

            tool_inputs = (
                json.loads(msg.get("tool_inputs", "[]"))
                if msg.get("tool_inputs")
                else []
            )
            for ti in tool_inputs:
                input_data = ti.get("input", {})
                candidate_paths = [
                    str(input_data.get("file_path", "")),
                    str(input_data.get("path", "")),
                    str(input_data.get("filePath", "")),
                ]
                if any(file_path.lower() in p.lower() for p in candidate_paths):
                    sessions[sid]["operations"].append(
                        {
                            "tool": ti.get("name", ""),
                            "timestamp": msg.get("timestamp", ""),
                            "input_summary": {
                                k: str(v)[:100] for k, v in ti.get("input", {}).items()
                            },
                        }
                    )

        return {
            "file_path": file_path,
            "sessions": list(sessions.values()),
            "total_sessions": len(sessions),
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool
def get_tool_inputs(
    session_id: str,
    tool_name: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Get all tool inputs for a session, optionally filtered by tool name.

    Returns file paths, commands, and arguments for each tool invocation.

    Args:
        session_id: Session ID (full or prefix, minimum 8 characters)
        tool_name: Filter by specific tool name (e.g., "Write", "Edit", "Bash")
        limit: Maximum results to return (default 100)
    """
    try:
        if err := _validate_session_id(session_id):
            return {"error": err}

        engine = _get_engine()
        messages = engine.cache.get_messages_by_tool(session_id, tool_name)

        tool_inputs = []
        for msg in messages[:limit]:
            inputs = (
                json.loads(msg.get("tool_inputs", "[]"))
                if msg.get("tool_inputs")
                else []
            )
            timestamp = msg.get("timestamp", "")
            for ti in inputs:
                # Filter by tool_name if specified
                if tool_name and ti.get("name") != tool_name:
                    continue

                entry = {
                    "tool": ti.get("name", ""),
                    "timestamp": timestamp,
                }

                tool_input = ti.get("input", {})
                if tool_input.get("file_path"):
                    entry["file_path"] = tool_input["file_path"]
                if tool_input.get("command"):
                    entry["command"] = tool_input["command"]
                if tool_input.get("path"):
                    entry["path"] = tool_input["path"]
                if tool_input.get("query"):
                    entry["query"] = tool_input["query"]

                tool_inputs.append(entry)

        return {
            "session_id": session_id,
            "tool_inputs": tool_inputs,
            "count": len(tool_inputs),
        }
    except Exception as e:
        return {"error": str(e)}


def main() -> None:
    """Entry point for the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
