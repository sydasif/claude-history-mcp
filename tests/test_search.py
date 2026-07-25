import json
from datetime import datetime, timedelta, timezone

from claude_history_mcp.cache import CacheManager
from claude_history_mcp.search import SearchEngine


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
                "raw_json": "{}",
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
                "raw_json": "{}",
            },
            {
                "entry_type": "assistant",
                "timestamp": None,
                "uuid": "u2",
                "content_text": "hi",
                "raw_json": "{}",
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
                "raw_json": "{}",
            },
            {
                "entry_type": "assistant",
                "timestamp": None,
                "uuid": "u2",
                "content_text": "running command",
                "tool_names": json.dumps(["Read"]),
                "raw_json": "{}",
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
                "raw_json": "{}",
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


def test_get_session_stats_token_counts(tmp_path):
    engine = _engine(tmp_path)
    pid = engine.cache.upsert_project("/a", "a")
    engine.cache.upsert_session(
        pid, "s1", total_input_tokens=100, total_output_tokens=50, message_count=2
    )
    stats = engine.get_session_stats("s1")
    assert stats is not None
    assert stats["total_input_tokens"] == 100
    assert stats["total_output_tokens"] == 50


def test_get_session_stats_tool_usage(tmp_path):
    engine = _engine(tmp_path)
    pid = engine.cache.upsert_project("/a", "a")
    engine.cache.upsert_session(pid, "s1")
    engine.cache.insert_messages(
        pid,
        "s1",
        "s.jsonl",
        [
            {
                "entry_type": "assistant",
                "timestamp": None,
                "uuid": "u1",
                "content_text": "",
                "tool_names": json.dumps(["Bash", "Bash", "Read"]),
                "raw_json": "{}",
            }
        ],
    )
    stats = engine.get_session_stats("s1")
    assert stats is not None
    assert stats["tool_usage"]["Bash"] == 2
    assert stats["tool_usage"]["Read"] == 1


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


def test_get_recent_activity_includes_null_timestamps(tmp_path):
    """Regression test: `WHERE m.timestamp >= ?` silently drops NULL
    timestamps in SQL, contradicting spec 3.2's rule that timestamp-less
    entries always survive date filtering."""
    engine = _engine(tmp_path)
    pid = engine.cache.upsert_project("/a", "a")
    recent = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    engine.cache.insert_messages(
        pid,
        "s1",
        "s.jsonl",
        [
            {
                "entry_type": "user",
                "timestamp": recent,
                "uuid": "u1",
                "content_text": "recent one",
                "raw_json": "{}",
            },
            {
                "entry_type": "user",
                "timestamp": None,
                "uuid": "u2",
                "content_text": "no timestamp",
                "raw_json": "{}",
            },
        ],
    )
    result = engine.get_recent_activity(hours=24)
    texts = {r["text_preview"] for r in result}
    assert "recent one" in texts
    assert "no timestamp" in texts


def test_get_recent_activity_excludes_old(tmp_path):
    engine = _engine(tmp_path)
    pid = engine.cache.upsert_project("/a", "a")
    old = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    engine.cache.insert_messages(
        pid,
        "s1",
        "s.jsonl",
        [
            {
                "entry_type": "user",
                "timestamp": old,
                "uuid": "u1",
                "content_text": "old one",
                "raw_json": "{}",
            }
        ],
    )
    result = engine.get_recent_activity(hours=24)
    assert all(r["content_text"] != "old one" for r in result)


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
                "raw_json": "{}",
            }
        ],
    )

    cost = engine.get_cost_estimate(project="My Project")
    assert cost["total_input_tokens"] == 1000
    assert cost["total_output_tokens"] == 500
    assert cost["total_cost_usd"] > 0

    trends = engine.get_usage_trends(project="My Project")
    assert len(trends) == 1
    assert trends[0]["message_count"] == 1

    models = engine.get_model_usage(project="My Project")
    assert len(models) == 1
    assert models[0]["model"] == "claude-sonnet-5"

    tools = engine.get_tool_usage(project="My Project")
    tool_names = {t["tool_name"] for t in tools}
    assert "Read" in tool_names
    assert "Bash" in tool_names
