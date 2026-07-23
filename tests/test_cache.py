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


def test_upsert_project_updates_display_name(tmp_path):
    cache = _cache(tmp_path)
    pid1 = cache.upsert_project("/home/zulu/proj", "old-name")
    pid2 = cache.upsert_project("/home/zulu/proj", "new-name")
    assert pid1 == pid2
    assert cache.get_project("/home/zulu/proj")["display_name"] == "new-name"


def test_get_project_none_for_missing(tmp_path):
    cache = _cache(tmp_path)
    assert cache.get_project("/nope") is None


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
                "raw_json": "{}",
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
                "raw_json": "{}",
            },
            {
                "entry_type": "user",
                "timestamp": "2026-07-23T10:01:00",
                "uuid": "u2",
                "content_text": "completely unrelated text",
                "raw_json": "{}",
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
                "raw_json": "{}",
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
                "raw_json": "{}",
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
                "raw_json": "{}",
            },
            {
                "entry_type": "assistant",
                "timestamp": None,
                "uuid": "u2",
                "content_text": "second",
                "raw_json": "{}",
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
            {"display": "unrelated command", "project": "/a", "sessionId": "s1", "timestamp": 1001},
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
    assert cache.get_stats() == {"projects": 0, "sessions": 0, "messages": 0, "history_commands": 0}


def test_get_stats_counts(tmp_path):
    cache = _cache(tmp_path)
    pid = cache.upsert_project("/a", "a")
    cache.upsert_session(pid, "s1")
    stats = cache.get_stats()
    assert stats["projects"] == 1
    assert stats["sessions"] == 1


def test_transaction_commits_on_success(tmp_path):
    cache = _cache(tmp_path)
    with cache.transaction() as conn:
        conn.execute("INSERT INTO projects (project_path, display_name) VALUES (?, ?)", ("/a", "a"))
    assert cache.get_project("/a") is not None


def test_transaction_rolls_back_on_exception(tmp_path):
    cache = _cache(tmp_path)
    try:
        with cache.transaction() as conn:
            conn.execute(
                "INSERT INTO projects (project_path, display_name) VALUES (?, ?)", ("/a", "a")
            )
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert cache.get_project("/a") is None


def test_recompute_project_stats_rolls_up_from_sessions(tmp_path):
    """Regression test: projects.total_messages/total_input_tokens/
    total_output_tokens/earliest_timestamp/latest_timestamp were never
    written anywhere in the original blueprint, so list_projects() always
    reported zeros."""
    cache = _cache(tmp_path)
    pid = cache.upsert_project("/a", "a")
    cache.upsert_session(
        pid,
        "s1",
        message_count=5,
        total_input_tokens=100,
        total_output_tokens=50,
        first_timestamp="2026-07-01T00:00:00",
        last_timestamp="2026-07-02T00:00:00",
    )
    cache.upsert_session(
        pid,
        "s2",
        message_count=3,
        total_input_tokens=30,
        total_output_tokens=20,
        first_timestamp="2026-07-03T00:00:00",
        last_timestamp="2026-07-04T00:00:00",
    )
    cache.recompute_project_stats(pid)
    project = cache.get_project("/a")
    assert project["total_messages"] == 8
    assert project["total_input_tokens"] == 130
    assert project["total_output_tokens"] == 70
    assert project["earliest_timestamp"] == "2026-07-01T00:00:00"
    assert project["latest_timestamp"] == "2026-07-04T00:00:00"


def test_get_changed_files_detects_new_and_modified(tmp_path):
    cache = _cache(tmp_path)
    f = tmp_path / "s1.jsonl"
    f.write_text("{}")
    # Not tracked yet -> should be "changed"
    assert cache.get_changed_files([f]) == [f]
    cache.set_file_mtime(str(f), f.stat().st_mtime)
    # Now tracked and unchanged -> no changes
    assert cache.get_changed_files([f]) == []
