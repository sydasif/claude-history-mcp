"""Read JSONL files, parse using claude-code-log library, store searchable fields in our cache."""

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from claude_code_log.api import (
    load_transcript,
    load_directory_transcripts,
    load_history_file as lib_load_history_file,
    ensure_fresh_cache,
    CacheManager as LibCacheManager,
    SessionCacheData,
)
from .cache import CacheManager as OurCacheManager
from .discovery import discover_projects, _extract_display_name
from .utils import parse_timestamp


@dataclass
class LoadResult:
    session_id: str
    project_id: int
    parsed_entries: int
    error_entries: int
    first_user_message: str
    message_count: int
    total_input_tokens: int
    total_output_tokens: int


# Module-level cache for lib cache directory to avoid creating new temp dirs
_lib_cache_dir: str | None = None
_lib_cache_instance: LibCacheManager | None = None


def _get_lib_cache() -> LibCacheManager:
    """Get a library cache manager for parsing (uses temporary directory, reused)."""
    global _lib_cache_dir, _lib_cache_instance
    if _lib_cache_instance is None:
        _lib_cache_dir = tempfile.mkdtemp(prefix="claude-history-lib-cache-")
        _lib_cache_instance = LibCacheManager(Path(_lib_cache_dir), "1.5.0")
    return _lib_cache_instance


def load_jsonl_file(
    file_path: Path,
    cache: OurCacheManager,
    project_id: int,
) -> LoadResult:
    """Parse a single JSONL file using claude-code-log library and store in our cache."""
    session_id = file_path.stem
    parsed_entries = []
    first_user_message = ""
    message_count = 0
    total_input = 0
    total_output = 0
    errors = 0
    first_timestamp = None
    last_timestamp = None
    cwd = None
    summary = None

    # Read and parse lines manually for error tracking
    import json
    from claude_code_log.api import create_transcript_entry

    with file_path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                errors += 1
                continue

            # Use library's create_transcript_entry to validate
            # Skip known types that library doesn't handle but we don't care about
            entry_type = data.get("type", "")
            silent_skip_types = {
                "file-history-snapshot", "last-prompt", "permission-mode",
                "mode", "custom-title", "agent-name", "agent-color", "frame-link",
                "file-history-delta", "pr-link",
            }
            if entry_type in silent_skip_types:
                continue

            # Use library's create_transcript_entry to validate
            entry = create_transcript_entry(data)
            if entry is None:
                errors += 1
                continue

            # Extract metadata for session record
            ts = getattr(entry, "timestamp", None)
            if ts:
                dt = parse_timestamp(ts)
                if dt:
                    if first_timestamp is None or dt < first_timestamp:
                        first_timestamp = dt
                    if last_timestamp is None or dt > last_timestamp:
                        last_timestamp = dt

            # Extract cwd from user messages
            if hasattr(entry, "cwd") and entry.cwd and not cwd:
                cwd = entry.cwd

            # Extract summary
            if entry.type == "summary" and hasattr(entry, "summary"):
                summary = entry.summary

            # Extract first user message
            if entry.type == "user" and entry.message and not first_user_message:
                text = _extract_text_from_entry(entry)
                if text and not text.startswith("<"):
                    first_user_message = text[:500]

            # Count message entries
            if entry.type in ("user", "assistant", "attachment", "queue-operation"):
                message_count += 1

            # Get tokens
            inp, out = _get_tokens(entry)
            total_input += inp
            total_output += out

            # Build searchable record
            text = _get_entry_text(entry)
            tools = _extract_tools(entry)
            model = None
            is_error = 0
            if entry.type == "assistant":
                if entry.message and entry.message.model:
                    model = entry.message.model
                # Library uses requestId instead of error field
                if hasattr(entry, "requestId") and entry.requestId:
                    is_error = 1

            # Serialize entry to JSON
            try:
                raw_json = json.dumps(entry.model_dump() if hasattr(entry, "model_dump") else str(entry), ensure_ascii=False)
            except Exception:
                raw_json = str(entry)

            parsed_entries.append(
                {
                    "entry_type": entry.type,
                    "timestamp": getattr(entry, "timestamp", None),
                    "uuid": getattr(entry, "uuid", None),
                    "parent_uuid": getattr(entry, "parentUuid", None),
                    "is_sidechain": 1 if getattr(entry, "isSidechain", False) else 0,
                    "content_text": text,
                    "tool_names": json.dumps(tools),
                    "model": model,
                    "tokens_input": inp,
                    "tokens_output": out,
                    "is_error": is_error,
                    "raw_json": raw_json,
                }
            )

    # Store in our cache
    if parsed_entries:
        cache.insert_messages(project_id, session_id, file_path.name, parsed_entries)

    # Upsert session metadata
    cache.upsert_session(
        project_id,
        session_id,
        summary=summary,
        ai_title=None,  # We don't have ai-title yet
        first_timestamp=first_timestamp.isoformat() if first_timestamp else None,
        last_timestamp=last_timestamp.isoformat() if last_timestamp else None,
        message_count=message_count,
        first_user_message=first_user_message[:500] if first_user_message else None,
        cwd=cwd,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
    )

    return LoadResult(
        session_id=session_id,
        project_id=project_id,
        parsed_entries=len(parsed_entries),
        error_entries=errors,
        first_user_message=first_user_message[:200],
        message_count=message_count,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
    )


def load_history_file(file_path: Path, cache: OurCacheManager) -> int:
    """Parse history.jsonl and store commands in our cache."""
    import json
    from .utils import scrub_surrogates

    commands = []
    with file_path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            commands.append(
                {
                    "display": scrub_surrogates(data.get("display", "")) or "",
                    "project": data.get("project", ""),
                    "sessionId": data.get("sessionId", ""),
                    "timestamp": data.get("timestamp", 0),
                }
            )
    if not commands:
        return 0
    return cache.insert_history_commands(commands)


def load_project(
    project_path: Path,
    cache: OurCacheManager,
    force: bool = False,
) -> list[LoadResult]:
    """Load all JSONL files in a project directory, reparsing only changed files."""
    jsonl_files = sorted(project_path.glob("*.jsonl"))
    if not jsonl_files:
        return []

    display_name = _extract_display_name(jsonl_files[0]) or project_path.name
    project_id = cache.upsert_project(str(project_path), display_name)

    files_to_load = jsonl_files
    if not force:
        files_to_load = cache.get_changed_files(jsonl_files)
        if not files_to_load:
            return []

    results = []
    for jsonl_file in files_to_load:
        # Clear old messages for this session before reloading
        cache.clear_project_messages(project_id, session_id=jsonl_file.stem)
        result = load_jsonl_file(jsonl_file, cache, project_id)
        cache.set_file_mtime(str(jsonl_file), jsonl_file.stat().st_mtime)
        results.append(result)

    # Roll session aggregates up to the project row
    cache.recompute_project_stats(project_id)

    return results


def load_all_projects(
    cache: OurCacheManager,
    projects_dir: Path | None = None,
    force: bool = False,
) -> list[LoadResult]:
    """Load all projects into cache."""
    all_results = []
    for project in discover_projects(projects_dir):
        results = load_project(project.path, cache, force=force)
        all_results.extend(results)
    return all_results


def _extract_text_from_entry(entry) -> str:
    """Extract text content from an entry's message."""
    if not hasattr(entry, "message") or not entry.message:
        return ""
    if not hasattr(entry.message, "content") or not entry.message.content:
        return ""
    parts = []
    for item in entry.message.content:
        if hasattr(item, "type") and item.type == "text" and hasattr(item, "text"):
            parts.append(item.text)
    return "\n".join(parts)


def _get_tokens(entry) -> tuple[int, int]:
    """Get (input_tokens, output_tokens) from an entry."""
    if hasattr(entry, "message") and entry.message and hasattr(entry.message, "usage") and entry.message.usage:
        usage = entry.message.usage
        return (usage.input_tokens or 0, usage.output_tokens or 0)
    return (0, 0)


def _get_entry_text(entry) -> str:
    """Get searchable text from any entry type."""
    if hasattr(entry, "message") and entry.message and hasattr(entry.message, "content") and entry.message.content:
        return _extract_text_from_entry(entry)
    if entry.type == "system" and hasattr(entry, "content") and entry.content:
        return entry.content
    if entry.type == "summary" and hasattr(entry, "summary"):
        return entry.summary
    if entry.type == "ai-title" and hasattr(entry, "aiTitle"):
        return entry.aiTitle
    return ""


def _extract_tools(entry) -> list[str]:
    """Extract tool names from an entry."""
    if not hasattr(entry, "message") or not entry.message or not hasattr(entry.message, "content"):
        return []
    tools = []
    for item in entry.message.content:
        if hasattr(item, "type") and item.type == "tool_use" and hasattr(item, "name"):
            tools.append(item.name)
    return tools