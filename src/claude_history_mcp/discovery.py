"""Discover Claude Code project directories and session JSONL files."""

import json
from dataclasses import dataclass
from pathlib import Path

from .utils import get_projects_dir


@dataclass(slots=True)
class ProjectInfo:
    display_name: str  # human-readable from cwd field
    path: Path  # full path to project dir
    jsonl_files: list[Path]


@dataclass(slots=True)
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
    for entry in projects_dir.iterdir():
        if entry.is_dir() and not entry.name.startswith("."):
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




def _extract_display_name(jsonl_path: Path) -> str | None:
    """Read the cwd field from the first line (of the first 20) that has one."""
    try:
        with Path(jsonl_path).open(encoding="utf-8", errors="replace") as f:
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
                    return str(data["cwd"])
    except OSError:
        pass
    return None
