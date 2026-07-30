"""Memory tools for Claude History MCP.

Wraps the existing markdown memory graph that Claude Code auto-generates under
projects/<project>/memory/. Adds two tools:

- retain: write a new memory note grounded in specific JSONL sessions
- reflect: gather evidence from memory notes + JSONL and return a structured bundle

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

from .utils import scrub_surrogates

from .engine import get_engine as _get_search_engine

logger = logging.getLogger(__name__)

_MEMORY_DIR = "memory"
_MEMORY_INDEX = "MEMORY.md"
_FRONTMATTER_RE = re.compile(r"^---\n.*?\n---", re.DOTALL)
_NAME_RE = re.compile(r"^name:\s*(.+)$", re.MULTILINE)


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

    note_existed = note_path.exists()
    _write_markdown(note_path, full)
    if not note_existed:
        _update_memory_index(project_dir, safe_name, description)

    return {
        "name": safe_name,
        "path": str(note_path),
        "description": _yaml_escape(description),
        "created": datetime.now(UTC).isoformat(),
    }


def _yaml_escape(s: str) -> str:
    """Minimal YAML escaping for safe string representation."""
    if not s:
        return ""
    return s.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


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
        desc = _yaml_escape(description or statement[:120])
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

        for note in notes[:10]:
            text = _read_markdown(Path(note["path"]))
            front = _parse_frontmatter(text)
            body = (
                _FRONTMATTER_RE.sub("", text).strip()
                if _FRONTMATTER_RE.search(text)
                else text
            )
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
