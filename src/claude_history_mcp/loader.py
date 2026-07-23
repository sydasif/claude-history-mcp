"""Read JSONL files, parse into typed entries, store searchable fields in cache."""

import json
from dataclasses import dataclass
from pathlib import Path

from .cache import CacheManager
from .discovery import _extract_display_name, discover_projects
from .models import AiTitleEntry, AssistantEntry, AttachmentEntry, QueueOperationEntry, SummaryEntry, UserEntry
from .parser import create_entry, extract_text, extract_tool_names, get_entry_text, get_entry_tokens, parse_timestamp
from .utils import get_projects_dir, scrub_surrogates


@dataclass
class LoadResult:
    session_id: str
    project_id: int
    total_entries: int
    parsed_entries: int
    skipped_entries: int
    error_entries: int
    first_user_message: str
    message_count: int
    total_input_tokens: int
    total_output_tokens: int


_MESSAGE_ENTRY_TYPES = (UserEntry, AssistantEntry, AttachmentEntry, QueueOperationEntry)


def load_jsonl_file(
    file_path: Path,
    cache: CacheManager,
    project_id: int,
) -> LoadResult:
    """Parse a single JSONL file and store in cache."""
    session_id = file_path.stem
    parsed_entries = []
    first_user_message = ""
    message_count = 0
    total_input = 0
    total_output = 0
    skipped = 0
    errors = 0
    first_timestamp = None
    last_timestamp = None
    cwd = None
    summary = None
    ai_title = None

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                errors += 1
                continue

            entry = create_entry(data)
            if entry is None:
                skipped += 1
                continue

            # Extract metadata for session record
            ts = parse_timestamp(entry.timestamp)
            if ts:
                if first_timestamp is None or ts < first_timestamp:
                    first_timestamp = ts
                if last_timestamp is None or ts > last_timestamp:
                    last_timestamp = ts

            if isinstance(entry, UserEntry):
                if not cwd and entry.cwd:
                    cwd = entry.cwd
                if entry.message and not first_user_message:
                    text = extract_text(entry.message.content)
                    if text and not text.startswith("<"):
                        first_user_message = text[:500]

            inp, out = 0, 0
            if isinstance(entry, _MESSAGE_ENTRY_TYPES):
                message_count += 1
                inp, out = get_entry_tokens(entry)
                total_input += inp
                total_output += out

            if isinstance(entry, SummaryEntry):
                summary = entry.summary

            if isinstance(entry, AiTitleEntry):
                ai_title = entry.aiTitle

            # Build searchable record
            text = get_entry_text(entry)
            tools: list[str] = []
            if isinstance(entry, _MESSAGE_ENTRY_TYPES) and entry.message:
                tools = extract_tool_names(entry.message.content)

            model = None
            is_error = 0
            if isinstance(entry, AssistantEntry):
                if entry.message:
                    model = entry.message.model
                if entry.error:
                    is_error = 1

            parsed_entries.append(
                {
                    "entry_type": entry.type,
                    "timestamp": scrub_surrogates(entry.timestamp),
                    "uuid": entry.uuid,
                    "parent_uuid": getattr(entry, "parentUuid", None),
                    "is_sidechain": 1 if getattr(entry, "isSidechain", False) else 0,
                    "content_text": scrub_surrogates(text),
                    "tool_names": json.dumps(tools),
                    "model": model,
                    "tokens_input": inp,
                    "tokens_output": out,
                    "is_error": is_error,
                    "raw_json": json.dumps(data, ensure_ascii=False),
                }
            )

    # Store in cache
    if parsed_entries:
        cache.insert_messages(project_id, session_id, file_path.name, parsed_entries)

    # Upsert session metadata
    cache.upsert_session(
        project_id,
        session_id,
        summary=scrub_surrogates(summary),
        ai_title=scrub_surrogates(ai_title),
        first_timestamp=first_timestamp.isoformat() if first_timestamp else None,
        last_timestamp=last_timestamp.isoformat() if last_timestamp else None,
        message_count=message_count,
        first_user_message=scrub_surrogates(first_user_message[:500] if first_user_message else None),
        cwd=cwd,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
    )

    return LoadResult(
        session_id=session_id,
        project_id=project_id,
        total_entries=message_count + skipped + errors,
        parsed_entries=len(parsed_entries),
        skipped_entries=skipped,
        error_entries=errors,
        first_user_message=first_user_message[:200],
        message_count=message_count,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
    )


def load_history_file(file_path: Path, cache: CacheManager) -> int:
    """Parse history.jsonl and store commands. Returns count of *new* rows inserted.

    Idempotent: relies on the UNIQUE constraint + INSERT OR IGNORE in
    CacheManager.insert_history_commands, since history.jsonl is append-only
    and reloaded on every server start (it isn't mtime-tracked like session
    files are).
    """
    commands = []
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
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
    cache: CacheManager,
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
        # Clear old messages for this file's session before reloading, so
        # re-running load doesn't duplicate rows.
        cache.clear_project_messages(project_id, session_id=jsonl_file.stem)
        result = load_jsonl_file(jsonl_file, cache, project_id)
        cache.set_file_mtime(str(jsonl_file), jsonl_file.stat().st_mtime)
        results.append(result)

    # Roll session aggregates up to the project row (fix: previously never
    # written, so list_projects() always reported zero messages/tokens).
    cache.recompute_project_stats(project_id)

    return results


def load_all_projects(
    cache: CacheManager,
    projects_dir: Path | None = None,
    force: bool = False,
) -> list[LoadResult]:
    """Load all projects into cache."""
    if projects_dir is None:
        projects_dir = get_projects_dir()

    all_results = []
    for project in discover_projects(projects_dir):
        results = load_project(project.path, cache, force=force)
        all_results.extend(results)
    return all_results
