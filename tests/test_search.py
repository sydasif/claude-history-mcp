import json
from datetime import UTC, datetime

from claude_history_mcp.cache import CacheManager
from claude_history_mcp.search import (
    SearchEngine,
    _aggregate_model_usage,
    _entry_type_to_role,
    _filter_results_by_date,
    _filter_sessions_by_date,
    _filter_sessions_by_project,
    _format_message_result,
    _resolve_project_id,
)


def _engine(tmp_path):
    return SearchEngine(CacheManager(tmp_path / "db.sqlite"))


def test_list_projects(tmp_path):
    engine = _engine(tmp_path)
    engine.cache.upsert_project("/a", "a")
    assert len(engine.list_projects()) == 1


def test_list_sessions(tmp_path):
    engine = _engine(tmp_path)
    pid = engine.cache.upsert_project("/a", "a")
    engine.cache.upsert_session(pid, "s1", last_timestamp="2026-07-23T10:00:00")
    assert len(engine.list_sessions()) == 1


def test_list_sessions_project_filter(tmp_path):
    engine = _engine(tmp_path)
    pid_a = engine.cache.upsert_project("/a", "proj-a")
    pid_b = engine.cache.upsert_project("/b", "proj-b")
    engine.cache.upsert_session(pid_a, "s1")
    engine.cache.upsert_session(pid_b, "s2")
    result = engine.list_sessions(project="proj-a")
    assert len(result) == 1
    assert result[0]["session_id"] == "s1"


def test_list_sessions_date_filter(tmp_path):
    engine = _engine(tmp_path)
    pid = engine.cache.upsert_project("/a", "a")
    engine.cache.upsert_session(pid, "old", last_timestamp="2020-01-01T00:00:00")
    engine.cache.upsert_session(pid, "new", last_timestamp="2026-07-23T00:00:00")
    result = engine.list_sessions(from_date="2025-01-01")
    ids = {s["session_id"] for s in result}
    assert "new" in ids
    assert "old" not in ids


def test_search_messages_finds_text(tmp_path):
    engine = _engine(tmp_path)
    pid = engine.cache.upsert_project("/a", "a")
    engine.cache.insert_messages(
        pid,
        "s1",
        "s1.jsonl",
        [
            {
                "entry_type": "user",
                "timestamp": None,
                "uuid": "u1",
                "content_text": "litellm proxy setup",
            }
        ],
    )
    result = engine.search_messages("litellm")
    assert len(result) == 1


def test_search_messages_role_filter(tmp_path):
    engine = _engine(tmp_path)
    pid = engine.cache.upsert_project("/a", "a")
    engine.cache.insert_messages(
        pid,
        "s1",
        "s1.jsonl",
        [
            {
                "entry_type": "user",
                "timestamp": None,
                "uuid": "u1",
                "content_text": "hi",
            },
            {
                "entry_type": "assistant",
                "timestamp": None,
                "uuid": "u2",
                "content_text": "hi",
            },
        ],
    )
    result = engine.search_messages("hi", role="user")
    assert len(result) == 1
    assert result[0]["role"] == "user"


def test_search_messages_tool_name_filter(tmp_path):
    engine = _engine(tmp_path)
    pid = engine.cache.upsert_project("/a", "a")
    engine.cache.insert_messages(
        pid,
        "s1",
        "s1.jsonl",
        [
            {
                "entry_type": "assistant",
                "timestamp": None,
                "uuid": "u1",
                "content_text": "running command",
                "tool_names": json.dumps(["Bash"]),
            },
            {
                "entry_type": "assistant",
                "timestamp": None,
                "uuid": "u2",
                "content_text": "running command",
                "tool_names": json.dumps(["Read"]),
            },
        ],
    )
    result = engine.search_messages("running", tool_name="Bash")
    assert len(result) == 1


def test_get_session_full_conversation(tmp_path):
    engine = _engine(tmp_path)
    pid = engine.cache.upsert_project("/a", "a")
    engine.cache.upsert_session(pid, "sess1")
    engine.cache.insert_messages(
        pid,
        "sess1",
        "s.jsonl",
        [
            {
                "entry_type": "user",
                "timestamp": None,
                "uuid": "u1",
                "content_text": "hi",
            }
        ],
    )
    result = engine.get_session("sess1")
    assert result is not None
    assert len(result["messages"]) == 1


def test_get_session_prefix_match(tmp_path):
    engine = _engine(tmp_path)
    pid = engine.cache.upsert_project("/a", "a")
    engine.cache.upsert_session(pid, "abcdef1234567890")
    result = engine.get_session("abcdef12")
    assert result is not None
    assert result["session"]["session_id"] == "abcdef1234567890"


def test_get_session_nonexistent(tmp_path):
    engine = _engine(tmp_path)
    assert engine.get_session("doesnotexist") is None


def test_search_history_finds_commands(tmp_path):
    engine = _engine(tmp_path)
    engine.cache.insert_history_commands(
        [
            {
                "display": "search for litellm",
                "project": "/a",
                "sessionId": "s1",
                "timestamp": 1000,
            }
        ]
    )
    assert len(engine.search_history("litellm")) == 1


def test_analytics_methods(tmp_path):
    engine = _engine(tmp_path)
    pid = engine.cache.upsert_project("/proj", "My Project")
    engine.cache.upsert_session(pid, "sess1")
    engine.cache.insert_messages(
        pid,
        "sess1",
        "s.jsonl",
        [
            {
                "entry_type": "assistant",
                "timestamp": "2026-07-25T10:00:00Z",
                "uuid": "u1",
                "content_text": "hello",
                "tool_names": json.dumps(["Read", "Bash"]),
                "model": "claude-sonnet-5",
                "tokens_input": 1000,
                "tokens_output": 500,
            }
        ],
    )

    models = engine.get_model_usage(project="My Project")
    assert len(models) == 1
    assert models[0]["model"] == "claude-sonnet-5"
# ---------------------------------------------------------------------------
# Pure function tests (no mocks, no I/O)
# ---------------------------------------------------------------------------


def test_entry_type_to_role_known():
    assert _entry_type_to_role("user") == "user"
    assert _entry_type_to_role("assistant") == "assistant"
    assert _entry_type_to_role("system") == "system"


def test_entry_type_to_role_unknown():
    assert _entry_type_to_role("tool_result") == "tool_result"
    assert _entry_type_to_role(None) == "unknown"
    assert _entry_type_to_role("") == "unknown"


def test_filter_sessions_by_project():
    sessions = [
        {"session_id": "a", "project_path": "/x/myproj", "display_name": "MyProj"},
        {"session_id": "b", "project_path": "/x/other", "display_name": "Other"},
    ]
    assert len(_filter_sessions_by_project(sessions, "myproj")) == 1
    assert _filter_sessions_by_project(sessions, "myproj")[0]["session_id"] == "a"
    assert len(_filter_sessions_by_project(sessions, "nonexistent")) == 0


def test_filter_sessions_by_date_inclusive():
    sessions = [
        {"session_id": "old", "last_timestamp": "2026-01-10T12:00:00"},
        {"session_id": "edge", "last_timestamp": "2026-01-15T12:00:00"},
        {"session_id": "new", "last_timestamp": "2026-01-20T12:00:00"},
        {"session_id": "no-ts", "last_timestamp": None},
    ]
    from_dt = datetime(2026, 1, 15, tzinfo=UTC).replace(tzinfo=None)
    to_dt = datetime(2026, 1, 20, tzinfo=UTC).replace(tzinfo=None)
    kept = _filter_sessions_by_date(sessions, from_dt, to_dt)
    ids = {s["session_id"] for s in kept}
    assert ids == {"edge", "no-ts"}


def test_filter_sessions_by_date_none_passthrough():
    sessions = [{"session_id": "a"}]
    assert _filter_sessions_by_date(sessions, None, None) == sessions


def test_format_message_result():
    row = {
        "session_id": "s1",
        "project_path": "/p",
        "timestamp": "2026-01-01T00:00:00",
        "entry_type": "user",
        "content_text": "hello world",
        "tool_names": json.dumps(["Read"]),
        "model": "claude-sonnet-5",
        "tokens_input": 10,
        "tokens_output": 5,
    }
    out = _format_message_result(row)
    assert out["role"] == "user"
    assert out["text_preview"] == "hello world"
    assert out["tool_names"] == ["Read"]


def test_format_message_result_empty_tool_names():
    row = {"entry_type": "assistant", "content_text": "", "tool_names": ""}
    out = _format_message_result(row)
    assert out["role"] == "assistant"
    assert out["text_preview"] == ""
    assert out["tool_names"] == []


def test_resolve_project_id():
    projects = [
        {"id": 1, "project_path": "/x/myproj", "display_name": "MyProj"},
        {"id": 2, "project_path": "/x/other", "display_name": "Other"},
    ]
    assert _resolve_project_id(projects, "myproj") == 1
    assert _resolve_project_id(projects, "nonexistent") is None
    assert _resolve_project_id(projects, "") is None


def test_filter_results_by_date_epoch():
    # epoch in ms; 2026-01-15T12:00:00Z
    ms = int(datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC).timestamp() * 1000)
    results = [
        {"session_id": "old", "timestamp_epoch": ms - 86400000},
        {"session_id": "new", "timestamp_epoch": ms + 86400000},
    ]
    from_dt = datetime(2026, 1, 15, tzinfo=UTC).replace(tzinfo=None)
    kept = _filter_results_by_date(results, from_dt, None)
    assert [r["session_id"] for r in kept] == ["new"]


def test_aggregate_model_usage_breakdown_only():
    rows = [
        {"model": "claude-sonnet-5", "input_tokens": 1_000_000, "output_tokens": 1_000_000},
        {"model": "claude-haiku-4-5", "input_tokens": 500_000, "output_tokens": 0},
    ]
    out = _aggregate_model_usage(rows, session_id=None, include_totals=False)
    assert len(out) == 2
    assert out[0]["model"] == "claude-sonnet-5"
    assert out[0]["estimated_cost_usd"] == 12.0  # 2 + 10
    assert out[1]["model"] == "claude-haiku-4-5"


def test_aggregate_model_usage_with_totals():
    rows = [
        {"model": "claude-sonnet-5", "input_tokens": 1_000_000, "output_tokens": 1_000_000},
    ]
    out = _aggregate_model_usage(rows, session_id=None, include_totals=True)
    assert out["total_cost_usd"] == 12.0
    assert out["total_input_tokens"] == 1_000_000
    assert out["total_output_tokens"] == 1_000_000
    assert out["cost_by_model"]["claude-sonnet-5"] == 12.0


def test_aggregate_model_usage_session_id_omits_breakdown():
    rows = [
        {"model": "claude-sonnet-5", "tokens_input": 1_000_000, "tokens_output": 1_000_000},
    ]
    out = _aggregate_model_usage(rows, session_id="s1", include_totals=True)
    assert out["breakdown"] == []
    assert out["total_cost_usd"] == 12.0
