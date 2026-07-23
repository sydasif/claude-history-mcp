"""Discover Claude Code project directories and session JSONL files."""

import json
from dataclasses import dataclass
from pathlib import Path

from .utils import get_projects_dir


@dataclass
class ProjectInfo:
    display_name: str  # human-readable from cwd field
    path: Path  # full path to project dir
    jsonl_files: list[Path]


@dataclass
class SessionFileInfo:
    session_id: str  # filename without .jsonl
    project: ProjectInfo
    file_path: Path
    file_size: int


def discover_projects(projects_dir: Path | None = None) -> list[ProjectInfo]:
    """Scan ~/.claude/projects/ for directories containing .jsonl files."""
    if projects_dir is None:
        projects_dir = get_projects_dir()
    if not projects_dir.exists():
        return []

    projects = []
    for entry in sorted(projects_dir.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        jsonl_files = sorted(entry.glob("*.jsonl"))
        if not jsonl_files:
            continue
        display_name = _extract_display_name(jsonl_files[0]) or entry.name
        projects.append(
            ProjectInfo(
                display_name=display_name,
                path=entry,
                jsonl_files=jsonl_files,
            )
        )
    return projects


def discover_all_sessions(projects_dir: Path | None = None) -> list[SessionFileInfo]:
    """List all session JSONL files across all projects."""
    sessions = []
    for project in discover_projects(projects_dir):
        for jsonl_file in project.jsonl_files:
            sessions.append(
                SessionFileInfo(
                    session_id=jsonl_file.stem,
                    project=project,
                    file_path=jsonl_file,
                    file_size=jsonl_file.stat().st_size,
                )
            )
    return sorted(sessions, key=lambda s: s.file_size, reverse=True)


def _extract_display_name(jsonl_path: Path) -> str | None:
    """Read the cwd field from the first line (of the first 20) that has one."""
    try:
        with open(jsonl_path, encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i >= 20:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if data.get("cwd"):
                    return data["cwd"]
    except OSError:
        pass
    return None
