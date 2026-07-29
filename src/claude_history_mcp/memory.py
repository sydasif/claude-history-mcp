"""Memory tools for Claude History MCP.

Wraps the existing markdown memory graph that Claude Code auto-generates under
projects/<project>/memory/. Adds three tools:

- retain: write a new memory note grounded in specific JSONL sessions
- reflect: gather evidence from memory notes + JSONL and return a structured bundle
- mental_model: pin a cached summary with auto-refresh on new session arrivals

No LLM dependency is added to the server. reflect returns structured evidence;
the calling Claude Code session does the synthesis.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .search import SearchEngine
from .utils import scrub_surrogates
from .memory_engine import MemoryDecayEngine

logger = logging.getLogger(__name__)

_MEMORY_DIR = "memory"
_MEMORY_INDEX = "MEMORY.md"
_FRONTMATTER_RE = re.compile(r"^---\n.*?\n---", re.DOTALL)
_NAME_RE = re.compile(r"^name:\s*(.+)$", re.MULTILINE)
_SCOPE_RE = re.compile(r"^scope:\s*(.+)$", re.MULTILINE)
_STALE_RE = re.compile(r"^stale:\s*(true|false)$", re.MULTILINE)
_LAST_REFRESHED_RE = re.compile(r"^last_refreshed:\s*(.+)$", re.MULTILINE)

# Global decay engine instance (per-process, like _engine in server.py)
_decay_engine: MemoryDecayEngine | None = None


def _get_decay_engine() -> MemoryDecayEngine:
    global _decay_engine
    if _decay_engine is None:
        _decay_engine = MemoryDecayEngine()
    return _decay_engine


def _claude_projects_root() -> Path:
    """Return ~/.claude/projects, respecting CLAUDE_PROJECTS_ROOT if set."""
    return Path(
        os.environ.get("CLAUDE_PROJECTS_ROOT", Path.home() / ".claude" / "projects")
    )


def _project_display_to_path(display_name: str) -> Path | None:
    """Resolve a project display name or path fragment to its actual directory.

    Matches against the encoded directory names under ~/.claude/projects/ by
    checking whether the decoded path contains the query string.
    """
    root = _claude_projects_root()
    if not root.exists():
        return None
    target = display_name.lower().strip("/")
    if target.startswith("-"):
        target = target[1:]
    for d in root.iterdir():
        if not d.is_dir():
            continue
        decoded = d.name
        if decoded.startswith("-"):
            decoded = decoded[1:]
        decoded = decoded.replace("--", "/")
        if target in decoded.lower():
            return d
    return None


def _read_markdown(path: Path) -> str:
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8")
    return scrub_surrogates(content) or ""


def _write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Minimal YAML-ish frontmatter parser - just grab key: value lines."""
    m = _FRONTMATTER_RE.search(text)
    if not m:
        return {}
    meta: dict[str, str] = {}
    for line in m.group().splitlines()[1:-1]:  # skip opening/closing ---
        line = line.strip()
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta


def _extract_name(text: str) -> str | None:
    m = _NAME_RE.search(text)
    return m.group(1).strip() if m else None


def _memory_dir_for_project(project_dir: Path) -> Path:
    return project_dir / _MEMORY_DIR


def _list_memory_notes(project_dir: Path) -> list[dict[str, str]]:
    """Return [{name, path, description}] for every markdown note in memory/."""
    mdir = _memory_dir_for_project(project_dir)
    notes: list[dict[str, str]] = []
    if not mdir.exists():
        return notes
    for f in sorted(mdir.glob("*.md")):
        if f.name == _MEMORY_INDEX:
            continue
        text = _read_markdown(f)
        name = _extract_name(text) or f.stem
        desc = ""
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("- [[") and " — " in line:
                desc = line.split(" — ", 1)[1].rstrip("]")
                break
        notes.append(
            {
                "name": name,
                "path": str(f),
                "description": desc,
            }
        )
    return notes


def _update_memory_index(project_dir: Path, note_name: str, description: str) -> None:
    """Add or update the [[wikilink]] entry in MEMORY.md."""
    index = _memory_dir_for_project(project_dir) / _MEMORY_INDEX
    existing = _read_markdown(index) if index.exists() else ""
    entry = f"- [[{note_name}]] — {description}"
    if entry in existing:
        return
    if existing.strip():
        new = existing.rstrip("\n") + f"\n{entry}\n"
    else:
        new = f"# Memory Index\n\n{entry}\n"
    _write_markdown(index, new)


def _find_note_path(project_dir: Path, name: str) -> Path | None:
    """Locate a memory note by its frontmatter name or filename stem."""
    mdir = _memory_dir_for_project(project_dir)
    for f in mdir.glob("*.md"):
        if f.name == _MEMORY_INDEX:
            continue
        text = _read_markdown(f)
        front = _parse_frontmatter(text)
        if front.get("name", f.stem) == name:
            return f
    return None


def _retain_note(
    project_dir: Path,
    name: str,
    description: str,
    content: str,
    session_ids: list[str] | None = None,
    note_type: str = "observation",
    related: list[str] | None = None,
) -> dict[str, Any]:
    """Write a memory note and update the index. Returns the note metadata."""
    safe_name = re.sub(r"[^a-z0-9-]", "-", name.lower().strip("-"))
    if not safe_name:
        safe_name = hashlib.sha1(name.encode()).hexdigest()[:10]

    mdir = _memory_dir_for_project(project_dir)
    note_path = mdir / f"{safe_name}.md"

    body_lines = [content.strip()]
    if session_ids:
        body_lines.append("")
        body_lines.append("**Sources:**")
        for sid in session_ids:
            body_lines.append(f"- Session `{sid}`")

    today = datetime.now(UTC).strftime("%Y-%m-%d")

    # Derive title from description/content, fallback to safe_name
    title = description.strip()
    if not title:
        title = content.strip().split("\n")[0][:80]
    if not title:
        title = safe_name.replace("-", " ").title()

    # Tags: accept note_type as a tag, cap at 3
    tags_raw = [note_type] if note_type else []
    tags_str = str(tags_raw[:3])

    # Related wikilinks: normalize to [[slug]] format, cap at reasonable limit
    related_links: list[str] = []
    if related:
        for ref in related[:10]:  # cap to prevent abuse
            ref = ref.strip()
            if not ref:
                continue
            # Already in [[slug]] form
            if ref.startswith("[[") and ref.endswith("]]"):
                related_links.append(ref)
            # Plain slug
            elif ref.startswith("- "):
                related_links.append(f"[[{ref[2:].strip()}]]")
            else:
                related_links.append(f"[[{ref}]]")
    related_yaml = str(related_links)

    frontmatter = "\n".join(
        [
            "---",
            f"name: {safe_name}",
            f"description: {description}",
            "metadata:",
            "  node_type: memory",
            f"  type: {note_type}",
            f"  originSessionId: {session_ids[0] if session_ids else 'unknown'}",
            f"title: {title}",
            f"tags: {tags_str}",
            f"created: {today}",
            f"last_update: {today}",
            f"related: {related_yaml}",
            "---",
        ]
    )

    body = "\n".join(body_lines) + "\n"
    full = frontmatter + "\n" + body

    if note_path.exists():
        _write_markdown(note_path, full)
    else:
        _write_markdown(note_path, full)
        _update_memory_index(project_dir, safe_name, description)

    # Register in decay engine (turn = days since epoch for monotonic advancement)
    turn = int(datetime.now(UTC).timestamp() // 86400)
    is_foundational = note_type in ("decision", "bug")  # decisions/bugs never decay
    engine = _get_decay_engine()
    engine.register(
        note_id=safe_name,
        content=content,
        current_turn=turn,
        is_foundational=is_foundational,
    )

    return {
        "name": safe_name,
        "path": str(note_path),
        "description": description,
        "created": datetime.now(UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# Public tool functions
# ---------------------------------------------------------------------------


def retain(
    project: str,
    statement: str,
    description: str = "",
    session_ids: list[str] | None = None,
    note_type: str = "observation",
    related: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Store a new memory note grounded in specific sessions.

    Args:
        project: Project display name or path fragment.
        statement: The natural language fact/decision/insight to store.
        description: One-line summary for the memory index.
        session_ids: Session UUIDs that support this statement.
        note_type: observation | world | experience | decision | bug.
        related: Optional list of related memory note names or [[wikilink]] refs.
    """
    try:
        project_dir = _project_display_to_path(project)
        if project_dir is None:
            return [{"error": f"Project not found: {project}"}]
        desc = description or statement[:120]
        result = _retain_note(
            project_dir=project_dir,
            name=desc[:80],
            description=desc,
            content=statement,
            session_ids=session_ids,
            note_type=note_type,
            related=related,
        )
        return [result]
    except Exception as e:
        logger.exception("retain failed")
        return [{"error": str(e)}]


def reflect(
    project: str,
    query: str,
    note_names: list[str] | None = None,
    session_ids: list[str] | None = None,
    session_limit: int = 5,
) -> list[dict[str, Any]]:
    """Gather structured evidence from memory notes and JSONL for synthesis.

    This does NOT call an LLM. It returns an evidence bundle that Claude Code
    reads and reasons over. The output shape is designed for the calling LLM
    to produce a sourced answer.

    Args:
        project: Project display name or path fragment.
        query: The question to gather evidence for.
        note_names: Specific memory notes to prioritize. None = all notes.
        session_ids: Specific sessions to pull verbatim evidence from.
        session_limit: Max sessions to include when session_ids is None.
    """
    try:
        project_dir = _project_display_to_path(project)
        if project_dir is None:
            return [{"error": f"Project not found: {project}"}]

        evidence: list[dict[str, Any]] = []

        # 1. Load targeted memory notes first - dense, pre-synthesized.
        notes = _list_memory_notes(project_dir)
        if note_names:
            notes = [n for n in notes if n["name"] in note_names]

        # Advance decay engine turn and evict stale notes
        turn = int(datetime.now(UTC).timestamp() // 86400)
        decay_engine = _get_decay_engine()
        decay_engine.step(turn)

        for note in notes[:10]:
            text = _read_markdown(Path(note["path"]))
            front = _parse_frontmatter(text)
            body = (
                _FRONTMATTER_RE.sub("", text).strip()
                if _FRONTMATTER_RE.search(text)
                else text
            )
            # Record recall for this note (boosts stability)
            decay_engine.recall(note["name"], turn)
            evidence.append(
                {
                    "type": "memory_note",
                    "name": note["name"],
                    "description": note.get("description", ""),
                    "path": note["path"],
                    "note_type": front.get("type", "unknown"),
                    "origin_session": front.get("originSessionId", ""),
                    "content": body[:4000],
                }
            )

        # 2. Pull JSONL turns as verbatim evidence.
        engine = _get_search_engine()
        sessions_queried: set[str] = set()

        if session_ids:
            targets = session_ids
        else:
            # Search recent sessions in this project that match the query.
            recent = engine.list_sessions(
                project=project,
                limit=max(session_limit, 10),
            )
            targets = [s.get("session_id", "") for s in recent if s.get("session_id")]

        for sid in targets[:session_limit]:
            if not sid or sid in sessions_queried:
                continue
            sessions_queried.add(sid)
            session_data = engine.get_session(sid)
            if not session_data or "messages" not in session_data:
                continue
            turns: list[dict[str, Any]] = []
            for msg in session_data["messages"]:
                text_content = msg.get("text", "")
                if not text_content or len(text_content) < 5:
                    continue
                turns.append(
                    {
                        "timestamp": msg.get("timestamp", ""),
                        "role": msg.get("role", "unknown"),
                        "text": text_content[:2000],
                        "tool_names": msg.get("tool_names", []),
                        "is_error": msg.get("is_error", False),
                    }
                )
            if turns:
                evidence.append(
                    {
                        "type": "jsonl_session",
                        "session_id": sid,
                        "project": session_data.get("display_name", project),
                        "cwd": session_data.get("cwd", ""),
                        "turn_count": len(turns),
                        "turns": turns[:20],
                    }
                )

        return [
            {
                "query": query,
                "project": project,
                "evidence": evidence,
                "synthesis_hint": (
                    "You are reasoning over the evidence above. "
                    "Cite memory_note paths and jsonl_session session_ids in your answer. "
                    "If evidence is insufficient, say so explicitly."
                ),
            }
        ]
    except Exception as e:
        logger.exception("reflect failed")
        return [{"error": str(e)}]


def mental_model(
    project: str,
    source_query: str,
    limit: int = 1,
) -> list[dict[str, Any]]:
    """Return the pinned mental model for a project, creating it if missing.

    A mental_model is a markdown note in memory/mental-models/ with
    `node_type: mental_model` frontmatter. Staleness is detected by
    comparing the project's JSONL file mtime fingerprint against the
    stored fingerprint in the model frontmatter - the same mechanism
    the loader uses for cache invalidation.

    Args:
        project: Project display name or path fragment.
        source_query: The question this model answers.
        limit: Max models to return.
    """
    try:
        project_dir = _project_display_to_path(project)
        if project_dir is None:
            return [{"error": f"Project not found: {project}"}]

        mdir = _memory_dir_for_project(project_dir)
        mm_dir = mdir / "mental-models"
        mm_dir.mkdir(parents=True, exist_ok=True)

        model_file = (
            mm_dir / f"{hashlib.sha1(source_query.encode()).hexdigest()[:12]}.md"
        )
        now = datetime.now(UTC).strftime("%Y-%m-%d")

        if model_file.exists():
            text = _read_markdown(model_file)
            front = _parse_frontmatter(text)
            body = (
                _FRONTMATTER_RE.sub("", text).strip()
                if _FRONTMATTER_RE.search(text)
                else text
            )

            stale_info = _check_mental_model_staleness(
                frontmatter=front,
                project_dir=project_dir,
            )
            stale = stale_info.get("stale", False)
            if stale and front.get("stale", "false").lower() != "true":
                _mark_model_stale(model_file)
                front["stale"] = "true"

            result = {
                "name": front.get("name", model_file.stem),
                "description": front.get("description", ""),
                "path": str(model_file),
                "source_query": front.get("source_query", source_query),
                "last_refreshed": front.get("last_refreshed", ""),
                "stale": stale,
                "scope": front.get("scope", ""),
                "content": body[:5000],
                "status": "stale" if stale else "current",
            }
            if stale:
                result["changed_since_refresh"] = stale_info.get("changed_files", [])
                result["refresh_hint"] = (
                    "Run memory_reflect on source_query to regenerate"
                )
            return [result]

        # No existing model - create a skeleton for the agent to fill.
        safe_name = re.sub(r"[^a-z0-9-]", "-", source_query.lower().strip("-"))[:60]
        if not safe_name:
            safe_name = model_file.stem

        fingerprint = _compute_mtime_fingerprint(project_dir)

        frontmatter = "\n".join(
            [
                "---",
                f"name: {safe_name}",
                f'description: "Cached answer for: {source_query[:100]}"',
                "metadata:",
                "  node_type: mental_model",
                "  type: project",
                f"  scope: {project_dir}",
                f'  source_query: "{source_query}"',
                f"  last_refreshed: {now}",
                "  stale: false",
                f'  mtime_fingerprint: "{fingerprint}"',
                "---",
            ]
        )
        body = (
            f"\n# {safe_name.replace('-', ' ').title()}\n\n"
            f"Source query: {source_query}\n\n"
            "Run reflect against this source_query to populate this model.\n"
        )
        _write_markdown(model_file, frontmatter + body)

        return [
            {
                "name": safe_name,
                "description": f"Cached answer for: {source_query[:100]}",
                "path": str(model_file),
                "source_query": source_query,
                "last_refreshed": now,
                "stale": False,
                "scope": str(project_dir),
                "content": body,
                "status": "created_empty",
            }
        ]
    except Exception as e:
        logger.exception("mental_model failed")
        return [{"error": str(e)}]


# ---------------------------------------------------------------------------
# Staleness helpers
# ---------------------------------------------------------------------------


def _compute_mtime_fingerprint(project_dir: Path) -> str:
    """Build a compact hash of all JSONL mtimes in a project directory.

    Mirrors the loader's mtime-tracking pattern: any change to a JSONL file
    will change this fingerprint, marking dependent mental models as stale.
    """
    import hashlib as _hashlib

    files = sorted(project_dir.glob("*.jsonl"))
    if not files:
        return _hashlib.sha256(b"").hexdigest()[:16]

    h = _hashlib.sha256()
    for fp in files:
        try:
            h.update(str(fp.name).encode())
            h.update(str(fp.stat().st_mtime_ns).encode())
        except OSError:
            continue
    return h.hexdigest()[:16]


def _check_mental_model_staleness(
    frontmatter: dict[str, str],
    project_dir: Path,
) -> dict[str, Any]:
    """Check whether the project's JSONL files changed since the model was saved.

    Uses an mtime fingerprint stored in the model frontmatter. If the current
    fingerprint differs, the model is stale. This mirrors the loader's
    `file_tracking`/`get_changed_files` invalidation logic.

    Returns {"stale": True, "changed_files": [...]} on mismatch,
    otherwise {"stale": False, "changed_files": []}.
    """
    stored_fp = frontmatter.get("mtime_fingerprint", "")
    current_fp = _compute_mtime_fingerprint(project_dir)

    if not stored_fp or stored_fp != current_fp:
        changed: list[str] = []
        if stored_fp:
            for fp in sorted(project_dir.glob("*.jsonl")):
                try:
                    changed.append(fp.name)
                except OSError:
                    continue
        return {"stale": True, "changed_files": changed}

    return {"stale": False, "changed_files": []}


def _mark_model_stale(model_file: Path) -> None:
    """Set stale: true in the model's frontmatter without touching the body."""
    text = _read_markdown(model_file)
    if "stale: false" in text:
        new_text = text.replace("stale: false", "stale: true", 1)
        _write_markdown(model_file, new_text)
    elif "stale: true" not in text:
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if line.strip() == "---":
                lines.insert(i + 1, "stale: true")
                break
        _write_markdown(model_file, "\n".join(lines))


# ---------------------------------------------------------------------------
# Lazy engine singleton (same pattern as server.py)
# ---------------------------------------------------------------------------

_engine: SearchEngine | None = None


def _get_search_engine() -> SearchEngine:
    global _engine
    if _engine is None:
        from . import initialize

        _engine = initialize()
    return _engine
