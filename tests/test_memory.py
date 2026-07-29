import json
import os
from pathlib import Path

import pytest

from claude_history_mcp.memory import mental_model, reflect, retain
from claude_history_mcp.cache import CacheManager
from claude_history_mcp.search import SearchEngine


@pytest.fixture(autouse=True)
def setup_scratch_home(tmp_path, monkeypatch):
    projects_dir = tmp_path / ".claude" / "projects"
    projects_dir.mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_PROJECTS_ROOT", str(projects_dir))

    # Also create a sample project directory
    proj_dir = projects_dir / "-home-zulu-testproj"
    proj_dir.mkdir(parents=True)

    # Create a sample JSONL session so reflect and fingerprint tests work
    session_file = proj_dir / "sess12345.jsonl"
    session_file.write_text(
        json.dumps(
            {
                "type": "user",
                "uuid": "u1",
                "sessionId": "sess12345",
                "timestamp": "2026-07-28T10:00:00Z",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "how do we configure proxy in litellm?",
                        }
                    ],
                },
            }
        )
        + "\n"
        + json.dumps(
            {
                "type": "assistant",
                "uuid": "a1",
                "sessionId": "sess12345",
                "timestamp": "2026-07-28T10:01:00Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": "You can set litellm_settings in config.yaml.",
                        }
                    ],
                },
            }
        )
        + "\n"
    )

    # Initialize DB and cache for search engine integration
    db_path = tmp_path / "db.sqlite"
    cache = CacheManager(db_path)
    pid = cache.upsert_project(str(proj_dir), "testproj")
    cache.upsert_session(pid, "sess12345", last_timestamp="2026-07-28T10:01:00Z")
    cache.insert_messages(
        pid,
        "sess12345",
        "sess12345.jsonl",
        [
            {
                "entry_type": "user",
                "timestamp": "2026-07-28T10:00:00Z",
                "uuid": "u1",
                "content_text": "how do we configure proxy in litellm?",
                "raw_json": "{}",
            },
            {
                "entry_type": "assistant",
                "timestamp": "2026-07-28T10:01:00Z",
                "uuid": "a1",
                "content_text": "You can set litellm_settings in config.yaml.",
                "tool_names": json.dumps(["Read"]),
                "raw_json": "{}",
            },
        ],
    )

    # Mock global SearchEngine in memory.py so it uses our test database
    import claude_history_mcp.memory as memory_module

    memory_module._engine = SearchEngine(cache)

    yield proj_dir

    memory_module._engine = None


def test_retain_creates_note_and_updates_index(setup_scratch_home):
    proj_dir = setup_scratch_home
    res = retain(
        project="testproj",
        statement="Always use uv for package management in Python projects.",
        description="Python package management standard",
        session_ids=["sess12345"],
        note_type="decision",
        related=["[[python-standards]]"],
    )
    assert len(res) == 1
    assert "error" not in res[0]
    assert res[0]["name"] == "python-package-management-standard"

    # Verify file exists
    note_path = Path(res[0]["path"])
    assert note_path.exists()
    content = note_path.read_text(encoding="utf-8")
    assert "Always use uv for package management" in content
    assert "sess12345" in content
    assert "decision" in content

    # Verify MEMORY.md index was updated
    index_path = proj_dir / "memory" / "MEMORY.md"
    assert index_path.exists()
    index_content = index_path.read_text(encoding="utf-8")
    assert "python-package-management-standard" in index_content
    assert "Python package management standard" in index_content


def test_retain_idempotent_index(setup_scratch_home):
    # Retain twice with same description
    retain(
        project="testproj",
        statement="First statement.",
        description="My Note",
    )
    retain(
        project="testproj",
        statement="Updated statement.",
        description="My Note",
    )

    index_path = setup_scratch_home / "memory" / "MEMORY.md"
    index_content = index_path.read_text(encoding="utf-8")
    # Should appear only once in MEMORY.md
    assert index_content.count("My Note") == 1


def test_retain_project_not_found():
    res = retain(project="nonexistent", statement="test")
    assert len(res) == 1
    assert "error" in res[0]


def test_reflect_gathers_evidence(setup_scratch_home):
    # First retain a note
    retain(
        project="testproj",
        statement="Database connection pooling is enabled.",
        description="DB Pooling",
        session_ids=["sess12345"],
        note_type="observation",
    )

    # Reflect
    res = reflect(
        project="testproj",
        query="How does database pooling work?",
        session_limit=5,
    )
    assert len(res) == 1
    bundle = res[0]
    assert bundle["query"] == "How does database pooling work?"
    assert len(bundle["evidence"]) >= 2

    # Check that we got both memory_note and jsonl_session evidence
    types = {e["type"] for e in bundle["evidence"]}
    assert "memory_note" in types
    assert "jsonl_session" in types


def test_reflect_project_not_found():
    res = reflect(project="missing", query="test")
    assert len(res) == 1
    assert "error" in res[0]


def test_mental_model_lifecycle(setup_scratch_home):
    # 1. Create mental model
    res = mental_model(
        project="testproj",
        source_query="What is the architecture of the project?",
    )
    assert len(res) == 1
    model = res[0]
    assert model["status"] == "created_empty"
    assert model["stale"] is False

    model_path = Path(model["path"])
    assert model_path.exists()

    # 2. Retrieve existing model (should be current)
    res2 = mental_model(
        project="testproj",
        source_query="What is the architecture of the project?",
    )
    assert len(res2) == 1
    assert res2[0]["status"] == "current"
    assert res2[0]["stale"] is False

    # 3. Modify session file mtime to trigger staleness detection
    session_file = setup_scratch_home / "sess12345.jsonl"
    # Touch file with future or past mtime
    os.utime(
        session_file, (session_file.stat().st_atime, session_file.stat().st_mtime + 100)
    )

    res3 = mental_model(
        project="testproj",
        source_query="What is the architecture of the project?",
    )
    assert len(res3) == 1
    assert res3[0]["stale"] is True
    assert res3[0]["status"] == "stale"
    assert "changed_since_refresh" in res3[0]


def test_mental_model_project_not_found():
    res = mental_model(project="missing", source_query="test")
    assert len(res) == 1
    assert "error" in res[0]
