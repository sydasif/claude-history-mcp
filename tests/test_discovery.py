import json

from claude_history_mcp.discovery import discover_projects


def _write_jsonl(path, lines):
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")


def test_discover_projects_empty_dir(tmp_path):
    assert discover_projects(tmp_path) == []


def test_discover_projects_finds_jsonl(tmp_path):
    proj = tmp_path / "-home-zulu-litellm-proxy"
    proj.mkdir()
    _write_jsonl(proj / "session1.jsonl", [{"type": "user", "cwd": "/home/zulu/litellm-proxy"}])

    projects = discover_projects(tmp_path)
    assert len(projects) == 1
    assert projects[0].display_name == "/home/zulu/litellm-proxy"


def test_discover_projects_skips_dir_without_jsonl(tmp_path):
    (tmp_path / "empty-dir").mkdir()
    assert discover_projects(tmp_path) == []


def test_discover_projects_skips_dot_dirs(tmp_path):
    (tmp_path / ".hidden").mkdir()
    _write_jsonl(tmp_path / ".hidden" / "s.jsonl", [{"type": "user"}])
    assert discover_projects(tmp_path) == []




def test_extract_display_name_checks_multiple_lines(tmp_path):
    """Regression: original blueprint's _extract_display_name broke out of
    the loop after the *first* line unconditionally, so a cwd on line 2+
    was never found despite the '# Only check first 20 lines' comment."""
    proj = tmp_path / "-home-zulu-proj"
    proj.mkdir()
    _write_jsonl(
        proj / "s1.jsonl",
        [
            {"type": "file-history-snapshot"},  # no cwd on line 1
            {"type": "user", "cwd": "/home/zulu/proj"},  # cwd on line 2
        ],
    )
    projects = discover_projects(tmp_path)
    assert projects[0].display_name == "/home/zulu/proj"
