from claude_history_mcp.cache import CacheManager


def _cache(tmp_path):
    return CacheManager(tmp_path / "test.db")


def test_cache_creates_db_file(tmp_path):
    cache = _cache(tmp_path)
    cache.connect()
    assert (tmp_path / "test.db").exists()


def test_upsert_project_inserts_and_returns_id(tmp_path):
    cache = _cache(tmp_path)
    pid = cache.upsert_project("/home/zulu/proj", "proj")
    assert isinstance(pid, int)


def test_get_all_projects(tmp_path):
    cache = _cache(tmp_path)
    cache.upsert_project("/a", "a")
    cache.upsert_project("/b", "b")
    assert len(cache.get_all_projects()) == 2


def test_upsert_session_inserts(tmp_path):
    cache = _cache(tmp_path)
    pid = cache.upsert_project("/a", "a")
    sid = cache.upsert_session(pid, "sess1", message_count=3)
    assert isinstance(sid, int)


def test_upsert_session_updates_fields(tmp_path):
    cache = _cache(tmp_path)
    pid = cache.upsert_project("/a", "a")
    cache.upsert_session(pid, "sess1", message_count=3)
    cache.upsert_session(pid, "sess1", message_count=7)
    sessions = cache.get_sessions()
    assert sessions[0]["message_count"] == 7


def test_get_sessions_includes_project_info(tmp_path):
    cache = _cache(tmp_path)
    pid = cache.upsert_project("/a", "display-a")
    cache.upsert_session(pid, "sess1")
    sessions = cache.get_sessions()
    assert sessions[0]["display_name"] == "display-a"


def test_get_session_by_id(tmp_path):
    cache = _cache(tmp_path)
    pid = cache.upsert_project("/a", "a")
    cache.upsert_session(pid, "sess1")
    session = cache.get_session("sess1")
    assert session is not None
    assert session["session_id"] == "sess1"


def test_insert_messages_stores_entries(tmp_path):
    cache = _cache(tmp_path)
    pid = cache.upsert_project("/a", "a")
    cache.insert_messages(
        pid,
        "sess1",
        "sess1.jsonl",
        [
            {
                "entry_type": "user",
                "timestamp": "2026-07-23T10:00:00",
                "uuid": "u1",
                "content_text": "hello world",
            }
        ],
    )
    msgs = cache.get_session_messages("sess1")
    assert len(msgs) == 1
    assert msgs[0]["content_text"] == "hello world"


def test_search_messages_finds_matching_content(tmp_path):
    """Regression test for the SQL string-concatenation bug: the original
    blueprint wrote `sql = "..."` followed by a bare string literal on the
    next line (not concatenated), which dropped the JOIN and WHERE clause
    and raised `no such column: p.project_path` on every call."""
    cache = _cache(tmp_path)
    pid = cache.upsert_project("/a", "display-a")
    cache.insert_messages(
        pid,
        "sess1",
        "sess1.jsonl",
        [
            {
                "entry_type": "user",
                "timestamp": "2026-07-23T10:00:00",
                "uuid": "u1",
                "content_text": "let's talk about litellm proxies",
            },
            {
                "entry_type": "user",
                "timestamp": "2026-07-23T10:01:00",
                "uuid": "u2",
                "content_text": "completely unrelated text",
            },
        ],
    )
    results = cache.search_messages("litellm")
    assert len(results) == 1
    assert results[0]["project_path"] == "/a"
    assert results[0]["display_name"] == "display-a"


def test_search_messages_with_project_filter(tmp_path):
    cache = _cache(tmp_path)
    pid_a = cache.upsert_project("/a", "a")
    pid_b = cache.upsert_project("/b", "b")
    cache.insert_messages(
        pid_a,
        "s1",
        "s1.jsonl",
        [
            {
                "entry_type": "user",
                "timestamp": None,
                "uuid": "u1",
                "content_text": "hi",
            }
        ],
    )
    cache.insert_messages(
        pid_b,
        "s2",
        "s2.jsonl",
        [
            {
                "entry_type": "user",
                "timestamp": None,
                "uuid": "u2",
                "content_text": "hi",
            }
        ],
    )
    results = cache.search_messages("hi", project_id=pid_a)
    assert len(results) == 1
    assert results[0]["session_id"] == "s1"


def test_search_messages_with_role_filter(tmp_path):
    cache = _cache(tmp_path)
    pid = cache.upsert_project("/a", "a")
    cache.insert_messages(
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
    results = cache.search_messages("hi", role="assistant")
    assert len(results) == 1
    assert results[0]["entry_type"] == "assistant"


def test_get_session_messages_ordered(tmp_path):
    cache = _cache(tmp_path)
    pid = cache.upsert_project("/a", "a")
    cache.insert_messages(
        pid,
        "s1",
        "s1.jsonl",
        [
            {
                "entry_type": "user",
                "timestamp": None,
                "uuid": "u1",
                "content_text": "first",
            },
            {
                "entry_type": "assistant",
                "timestamp": None,
                "uuid": "u2",
                "content_text": "second",
            },
        ],
    )
    msgs = cache.get_session_messages("s1")
    assert [m["content_text"] for m in msgs] == ["first", "second"]


def test_insert_history_commands(tmp_path):
    cache = _cache(tmp_path)
    n = cache.insert_history_commands(
        [{"display": "ls -la", "project": "/a", "sessionId": "s1", "timestamp": 1000}]
    )
    assert n == 1
    assert cache.get_stats()["history_commands"] == 1


def test_insert_history_commands_deduplicates(tmp_path):
    """Regression test: history.jsonl is reloaded on every server start with
    no mtime tracking, so without a UNIQUE constraint + INSERT OR IGNORE,
    every restart would duplicate the whole command history."""
    cache = _cache(tmp_path)
    cmd = {"display": "ls -la", "project": "/a", "sessionId": "s1", "timestamp": 1000}
    cache.insert_history_commands([cmd])
    cache.insert_history_commands([cmd])  # simulate a second server start
    assert cache.get_stats()["history_commands"] == 1


def test_search_history_finds_matching_display(tmp_path):
    cache = _cache(tmp_path)
    cache.insert_history_commands(
        [
            {
                "display": "search for litellm bug",
                "project": "/a",
                "sessionId": "s1",
                "timestamp": 1000,
            },
            {
                "display": "unrelated command",
                "project": "/a",
                "sessionId": "s1",
                "timestamp": 1001,
            },
        ]
    )
    results = cache.search_history("litellm")
    assert len(results) == 1


def test_search_history_with_project_filter(tmp_path):
    cache = _cache(tmp_path)
    cache.insert_history_commands(
        [
            {"display": "cmd", "project": "/a", "sessionId": "s1", "timestamp": 1000},
            {"display": "cmd", "project": "/b", "sessionId": "s2", "timestamp": 1001},
        ]
    )
    results = cache.search_history("cmd", project="/a")
    assert len(results) == 1
    assert results[0]["project"] == "/a"


def test_clear_all_empties_tables(tmp_path):
    cache = _cache(tmp_path)
    pid = cache.upsert_project("/a", "a")
    cache.upsert_session(pid, "s1")
    cache.clear_all()
    assert cache.get_stats() == {
        "projects": 0,
        "sessions": 0,
        "messages": 0,
        "history_commands": 0,
    }


def test_get_stats_counts(tmp_path):
    cache = _cache(tmp_path)
    pid = cache.upsert_project("/a", "a")
    cache.upsert_session(pid, "s1")
    stats = cache.get_stats()
    assert stats["projects"] == 1
    assert stats["sessions"] == 1


def test_get_changed_files_detects_new_and_modified(tmp_path):
    cache = _cache(tmp_path)
    f = tmp_path / "s1.jsonl"
    f.write_text("{}")
    # Not tracked yet -> should be "changed"
    assert cache.get_changed_files([f]) == [f]
    cache.set_file_mtime(str(f), f.stat().st_mtime)
    # Now tracked and unchanged -> no changes
    assert cache.get_changed_files([f]) == []


def test_fts5_available_after_connect(tmp_path):
    cache = _cache(tmp_path)
    cache.connect()
    assert getattr(cache, "_fts_available", False) is True


def test_fts5_search_finds_content(tmp_path):
    cache = _cache(tmp_path)
    pid = cache.upsert_project("/a", "a")
    cache.insert_messages(
        pid,
        "s1",
        "file.jsonl",
        [
            {
                "entry_type": "user",
                "timestamp": "2026-01-01T00:00:00Z",
                "uuid": "u1",
                "content_text": "find the payment bug",
            },
        ],
    )
    results = cache.search_messages("payment")
    assert len(results) == 1
    assert "payment" in results[0]["content_text"]


def test_fts5_clear_all_removes_index(tmp_path):
    cache = _cache(tmp_path)
    pid = cache.upsert_project("/a", "a")
    cache.insert_messages(
        pid,
        "s1",
        "file.jsonl",
        [
            {
                "entry_type": "user",
                "timestamp": "2026-01-01T00:00:00Z",
                "uuid": "u1",
                "content_text": "test content",
            },
        ],
    )
    cache.clear_all()
    results = cache.search_messages("test")
    assert len(results) == 0
