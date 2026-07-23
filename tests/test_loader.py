import json

from claude_history_mcp.cache import CacheManager
from claude_history_mcp.loader import (
    load_all_projects,
    load_history_file,
    load_jsonl_file,
    load_project,
)


def _write_jsonl(path, lines):
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")


def _sample_lines():
    return [
        {
            "type": "user",
            "uuid": "u1",
            "cwd": "/home/zulu/proj",
            "timestamp": "2026-07-23T10:00:00Z",
            "message": {"role": "user", "content": [{"type": "text", "text": "hello there"}]},
        },
        {
            "type": "assistant",
            "uuid": "a1",
            "timestamp": "2026-07-23T10:01:00Z",
            "message": {
                "id": "m1",
                "role": "assistant",
                "model": "claude-sonnet-5",
                "content": [{"type": "text", "text": "hi back"}],
                "usage": {"input_tokens": 10, "output_tokens": 20},
            },
        },
    ]


def test_load_jsonl_file_parses_and_stores(tmp_path):
    cache = CacheManager(tmp_path / "db.sqlite")
    pid = cache.upsert_project("/home/zulu/proj", "proj")
    f = tmp_path / "sess1.jsonl"
    _write_jsonl(f, _sample_lines())

    load_jsonl_file(f, cache, pid)
    msgs = cache.get_session_messages("sess1")
    assert len(msgs) == 2


def test_load_jsonl_file_returns_correct_stats(tmp_path):
    cache = CacheManager(tmp_path / "db.sqlite")
    pid = cache.upsert_project("/home/zulu/proj", "proj")
    f = tmp_path / "sess1.jsonl"
    _write_jsonl(f, _sample_lines())

    result = load_jsonl_file(f, cache, pid)
    assert result.message_count == 2
    assert result.total_input_tokens == 10
    assert result.total_output_tokens == 20


def test_load_jsonl_file_empty(tmp_path):
    cache = CacheManager(tmp_path / "db.sqlite")
    pid = cache.upsert_project("/a", "a")
    f = tmp_path / "empty.jsonl"
    f.write_text("")
    result = load_jsonl_file(f, cache, pid)
    assert result.message_count == 0


def test_load_jsonl_file_malformed_lines_skipped(tmp_path):
    cache = CacheManager(tmp_path / "db.sqlite")
    pid = cache.upsert_project("/a", "a")
    f = tmp_path / "bad.jsonl"
    f.write_text('{"type": "user", "uuid": "u1"}\nnot json at all\n')
    result = load_jsonl_file(f, cache, pid)
    assert result.error_entries == 1


def test_load_jsonl_file_extracts_first_user_message(tmp_path):
    cache = CacheManager(tmp_path / "db.sqlite")
    pid = cache.upsert_project("/a", "a")
    f = tmp_path / "sess1.jsonl"
    _write_jsonl(f, _sample_lines())
    result = load_jsonl_file(f, cache, pid)
    assert "hello there" in result.first_user_message


def test_load_jsonl_file_computes_token_totals(tmp_path):
    cache = CacheManager(tmp_path / "db.sqlite")
    pid = cache.upsert_project("/a", "a")
    f = tmp_path / "sess1.jsonl"
    _write_jsonl(f, _sample_lines())
    load_jsonl_file(f, cache, pid)
    session = cache.get_session("sess1")
    assert session["total_input_tokens"] == 10
    assert session["total_output_tokens"] == 20


def test_load_jsonl_file_handles_missing_timestamps(tmp_path):
    cache = CacheManager(tmp_path / "db.sqlite")
    pid = cache.upsert_project("/a", "a")
    f = tmp_path / "sess1.jsonl"
    _write_jsonl(f, [{"type": "user", "uuid": "u1", "message": {"role": "user", "content": []}}])
    result = load_jsonl_file(f, cache, pid)
    assert result.message_count == 1


def test_load_history_file(tmp_path):
    cache = CacheManager(tmp_path / "db.sqlite")
    f = tmp_path / "history.jsonl"
    _write_jsonl(
        f,
        [
            {"display": "ls -la", "project": "/a", "sessionId": "s1", "timestamp": 1000},
            {"display": "cd /tmp", "project": "/a", "sessionId": "s1", "timestamp": 1001},
        ],
    )
    count = load_history_file(f, cache)
    assert count == 2


def test_load_history_file_idempotent_across_reloads(tmp_path):
    """Regression: history.jsonl has no mtime tracking and is reloaded every
    server start, so re-loading the same file must not duplicate rows."""
    cache = CacheManager(tmp_path / "db.sqlite")
    f = tmp_path / "history.jsonl"
    _write_jsonl(f, [{"display": "ls -la", "project": "/a", "sessionId": "s1", "timestamp": 1000}])
    load_history_file(f, cache)
    load_history_file(f, cache)
    assert cache.get_stats()["history_commands"] == 1


def test_load_project_rolls_up_project_stats(tmp_path):
    cache = CacheManager(tmp_path / "db.sqlite")
    proj_dir = tmp_path / "-home-zulu-proj"
    proj_dir.mkdir()
    _write_jsonl(proj_dir / "sess1.jsonl", _sample_lines())

    load_project(proj_dir, cache)
    project = cache.get_project(str(proj_dir))
    assert project["total_messages"] == 2
    assert project["total_input_tokens"] == 10


def test_load_project_skips_unchanged_files_on_second_call(tmp_path):
    cache = CacheManager(tmp_path / "db.sqlite")
    proj_dir = tmp_path / "-home-zulu-proj"
    proj_dir.mkdir()
    _write_jsonl(proj_dir / "sess1.jsonl", _sample_lines())

    load_project(proj_dir, cache)
    first_count = cache.get_stats()["messages"]
    # Second call without force and without file changes -> no reparse, no duplication
    load_project(proj_dir, cache)
    assert cache.get_stats()["messages"] == first_count


def test_load_all_projects(tmp_path):
    cache = CacheManager(tmp_path / "db.sqlite")
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    proj_dir = projects_dir / "-home-zulu-proj"
    proj_dir.mkdir()
    _write_jsonl(proj_dir / "sess1.jsonl", _sample_lines())

    results = load_all_projects(cache, projects_dir=projects_dir)
    assert len(results) == 1
