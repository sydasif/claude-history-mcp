"""Read JSONL files, parse into typed models, store searchable fields in cache."""

import json
from dataclasses import dataclass
from pathlib import Path

from .cache import CacheManager as OurCacheManager
from .discovery import discover_projects, _extract_display_name
from .models import SILENT_SKIP_TYPES
from .parser import (
    create_entry,
    extract_text,
    extract_tool_names,
    get_entry_text,
    get_entry_tokens,
)
from .utils import parse_timestamp, scrub_surrogates


@dataclass(slots=True)
class LoadResult:
    session_id: str
    project_id: int
    parsed_entries: int
    error_entries: int
    first_user_message: str
    message_count: int
    total_input_tokens: int
    total_output_tokens: int


def load_jsonl_file(
    file_path: Path,
    cache: OurCacheManager,
    project_id: int,
) -> LoadResult:
    """Parse a single JSONL file and store in our cache."""
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
    ai_title = None

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

            # Skip known types we don't care about
            entry_type = data.get("type", "")
            if entry_type in SILENT_SKIP_TYPES:
                continue

            # Parse into typed model
            entry = create_entry(data)
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
            if not cwd:
                cwd = getattr(entry, "cwd", None) or None

            # Extract summary
            if entry.type == "summary":
                summary = getattr(entry, "summary", None)

            # Extract ai-title (keep the latest one)
            if entry.type == "ai-title":
                ai_title = getattr(entry, "aiTitle", None)

            # Extract first user message
            msg = getattr(entry, "message", None)
            if entry.type == "user" and msg and not first_user_message:
                text = extract_text(getattr(msg, "content", None))
                if text and not text.startswith("<"):
                    first_user_message = text[:500]

            # Count message entries
            if entry.type in ("user", "assistant", "attachment", "queue-operation"):
                message_count += 1

            # Get tokens
            inp, out = get_entry_tokens(entry)
            total_input += inp
            total_output += out

            # Build searchable record
            text = get_entry_text(entry)
            tools = extract_tool_names(getattr(msg, "content", None)) if msg else []
            model = None
            is_error = 0
            if entry.type == "assistant":
                if msg and getattr(msg, "model", None):
                    model = msg.model
                # Library uses requestId instead of error field
                if getattr(entry, "requestId", None):
                    is_error = 1

            # Serialize entry to JSON
            try:
                raw_json = json.dumps(
                    entry.model_dump() if hasattr(entry, "model_dump") else str(entry),
                    ensure_ascii=False,
                )
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

            if len(parsed_entries) >= 500:
                cache.insert_messages(
                    project_id, session_id, file_path.name, parsed_entries
                )
                parsed_entries.clear()

    # Store remaining in our cache
    if parsed_entries:
        cache.insert_messages(project_id, session_id, file_path.name, parsed_entries)

    # Upsert session metadata
    cache.upsert_session(
        project_id,
        session_id,
        summary=summary,
        ai_title=ai_title,
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
