"""MCP server integration tests using FastMCP v3 Client (in-memory transport).

Regression note: the original blueprint's test suite treated
`client.call_tool(...)` as if it returned a plain list of content blocks
(`len(result)`, `result[0].text`, `isinstance(result, list)`). In the
installed fastmcp==3.4.4, `call_tool` returns a `CallToolResult` dataclass
with `.data` (the tool's structured return value, already deserialized),
`.content` (raw content blocks), and `.is_error`. These tests use `.data`
directly instead.
"""

import json
import os

import pytest
from fastmcp import Client

os.environ.setdefault("HOME", "/tmp/claude-history-mcp-test-home")


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Point ~/.claude at a scratch dir so tests never touch real user data."""
    monkeypatch.setenv("HOME", str(tmp_path))
    claude_dir = tmp_path / ".claude" / "projects" / "-tmp-demo"
    claude_dir.mkdir(parents=True)
    (claude_dir / "sess1234567890.jsonl").write_text(
        "\n".join(
            json.dumps(line)
            for line in [
                {
                    "type": "user",
                    "uuid": "u1",
                    "sessionId": "sess1234567890",
                    "parentUuid": None,
                    "isSidechain": False,
                    "userType": "external",
                    "cwd": "/tmp/demo",
                    "version": "1.0",
                    "timestamp": "2026-07-23T10:00:00Z",
                    "message": {
                        "role": "user",
                        "content": [{"type": "text", "text": "hello there"}],
                        "usage": None,
                    },
                },
                {
                    "type": "assistant",
                    "uuid": "a1",
                    "sessionId": "sess1234567890",
                    "parentUuid": "u1",
                    "isSidechain": False,
                    "userType": "external",
                    "cwd": "/tmp/demo",
                    "version": "1.0",
                    "timestamp": "2026-07-23T10:01:00Z",
                    "message": {
                        "id": "m1",
                        "type": "message",
                        "role": "assistant",
                        "model": "claude-sonnet-5",
                        "content": [{"type": "text", "text": "hi back"}],
                        "usage": {"input_tokens": 5, "output_tokens": 5},
                    },
                    "requestId": "req-1",
                },
            ]
        )
        + "\n"
    )
    # Session with tool_use blocks for file change tracking tests
    (claude_dir / "sess-tools-abc12345.jsonl").write_text(
        "\n".join(
            json.dumps(line)
            for line in [
                {
                    "type": "assistant",
                    "uuid": "t1",
                    "sessionId": "sess-tools-abc12345",
                    "parentUuid": None,
                    "isSidechain": False,
                    "cwd": "/tmp/demo",
                    "version": "1.0",
                    "timestamp": "2026-07-23T11:00:00Z",
                    "message": {
                        "id": "m-t1",
                        "type": "message",
                        "role": "assistant",
                        "model": "claude-sonnet-5",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "tool-read-1",
                                "name": "Read",
                                "input": {"file_path": "/tmp/demo/app.py"},
                            },
                            {
                                "type": "tool_use",
                                "id": "tool-write-1",
                                "name": "Write",
                                "input": {
                                    "file_path": "/tmp/demo/new_file.txt",
                                    "content": "file content here",
                                },
                            },
                        ],
                        "usage": {"input_tokens": 10, "output_tokens": 10},
                    },
                },
                {
                    "type": "assistant",
                    "uuid": "t2",
                    "sessionId": "sess-tools-abc12345",
                    "parentUuid": "t1",
                    "isSidechain": False,
                    "cwd": "/tmp/demo",
                    "version": "1.0",
                    "timestamp": "2026-07-23T11:01:00Z",
                    "message": {
                        "id": "m-t2",
                        "type": "message",
                        "role": "assistant",
                        "model": "claude-sonnet-5",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "tool-edit-1",
                                "name": "Edit",
                                "input": {
                                    "file_path": "/tmp/demo/app.py",
                                    "old_string": "def old():",
                                    "new_string": "def new():",
                                },
                            },
                            {
                                "type": "tool_use",
                                "id": "tool-bash-1",
                                "name": "Bash",
                                "input": {
                                    "command": "ls -la /tmp/demo",
                                    "description": "List files",
                                },
                            },
                        ],
                        "usage": {"input_tokens": 10, "output_tokens": 10},
                    },
                },
            ]
        )
        + "\n"
    )
    # Reset the module-level cached engine so it re-initializes against the
    # isolated HOME for each test.
    import claude_history_mcp.server as server_module

    server_module._engine = None
    yield
    server_module._engine = None


@pytest.mark.asyncio
async def test_list_sessions():
    from claude_history_mcp.server import mcp

    async with Client(mcp) as client:
        result = await client.call_tool("list_sessions", {"limit": 5})
        assert len(result.data) == 2  # Two test sessions


@pytest.mark.asyncio
async def test_search_messages():
    from claude_history_mcp.server import mcp

    async with Client(mcp) as client:
        result = await client.call_tool(
            "search_messages", {"query": "hello", "limit": 5}
        )
        assert len(result.data) == 1


@pytest.mark.asyncio
async def test_search_history_empty_is_fine():
    from claude_history_mcp.server import mcp

    async with Client(mcp) as client:
        result = await client.call_tool(
            "search_history", {"query": "model", "limit": 5}
        )
        assert isinstance(result.data, list)


@pytest.mark.asyncio
async def test_server_has_expected_tools():
    from claude_history_mcp.server import mcp

    async with Client(mcp) as client:
        tools = await client.list_tools()
        tool_names = [t.name for t in tools]
        expected = [
            "list_sessions",
            "get_session_transcript",
            "search_history",
            "search_messages",
            "get_model_usage",
            "memory_retain",
            "memory_reflect",
        ]
        for name in expected:
            assert name in tool_names, f"Missing tool: {name}"


@pytest.mark.asyncio
async def test_server_has_expected_resources():
    from claude_history_mcp.server import mcp

    async with Client(mcp) as client:
        resources = await client.list_resources()
        resource_uris = [str(r.uri) for r in resources]
        assert "claude://health" in resource_uris


@pytest.mark.asyncio
async def test_new_analytics_tools():
    from claude_history_mcp.server import mcp

    async with Client(mcp) as client:
        # Verify tools exist in list_tools
        tools = await client.list_tools()
        tool_names = [t.name for t in tools]
        assert "get_model_usage" in tool_names

        # Call them
        res_models = await client.call_tool("get_model_usage", {})
        assert isinstance(res_models.data, list)

        res_totals = await client.call_tool("get_model_usage", {"include_totals": True})
        assert isinstance(res_totals.data, list)
        assert len(res_totals.data) == 1
        assert "breakdown" in res_totals.data[0]
        assert "total_cost_usd" in res_totals.data[0]


@pytest.mark.asyncio
async def test_get_file_changes():
    from claude_history_mcp.server import mcp

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_file_changes", {"session_id": "sess-tools-abc12345"}
        )
        assert result.data is not None
        data = result.data
        assert data["session_id"] == "sess-tools-abc12345"
        assert "files" in data
        assert "summary" in data

        # Should have 3 unique file paths: app.py, new_file.txt, and bash command
        assert data["summary"]["files_modified"] >= 3
        assert data["summary"]["writes"] >= 1
        assert data["summary"]["edits"] >= 1
        assert data["summary"]["reads"] >= 1
        assert data["summary"]["bash_commands"] >= 1

        # Check specific files are tracked
        files = data["files"]
        assert "/tmp/demo/app.py" in files
        assert "/tmp/demo/new_file.txt" in files
        # app.py should have both Read and Edit
        app_ops = [op["tool"] for op in files["/tmp/demo/app.py"]]
        assert "Read" in app_ops
        assert "Edit" in app_ops


@pytest.mark.asyncio
async def test_get_file_changes_short_session_id():
    from claude_history_mcp.server import mcp

    async with Client(mcp) as client:
        result = await client.call_tool("get_file_changes", {"session_id": "short"})
        assert result.data is not None
        assert "error" in result.data
        assert "8 characters" in result.data["error"]


@pytest.mark.asyncio
async def test_search_file_changes():
    from claude_history_mcp.server import mcp

    async with Client(mcp) as client:
        result = await client.call_tool("search_file_changes", {"file_path": "app.py"})
        assert result.data is not None
        data = result.data
        assert data["file_path"] == "app.py"
        assert "sessions" in data
        assert "total_sessions" in data
        assert data["total_sessions"] >= 1

        # Find our test session
        session_ids = [s["session_id"] for s in data["sessions"]]
        assert "sess-tools-abc12345" in session_ids


@pytest.mark.asyncio
async def test_get_tool_inputs():
    from claude_history_mcp.server import mcp

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_tool_inputs", {"session_id": "sess-tools-abc12345"}
        )
        assert result.data is not None
        data = result.data
        assert data["session_id"] == "sess-tools-abc12345"
        assert "tool_inputs" in data
        assert "count" in data
        assert data["count"] == 4  # Read, Write, Edit, Bash

        # Check Write has file_path
        writes = [t for t in data["tool_inputs"] if t["tool"] == "Write"]
        assert len(writes) == 1
        assert writes[0]["file_path"] == "/tmp/demo/new_file.txt"

        # Check Bash has command
        bash = [t for t in data["tool_inputs"] if t["tool"] == "Bash"]
        assert len(bash) == 1
        assert bash[0]["command"] == "ls -la /tmp/demo"


@pytest.mark.asyncio
async def test_get_tool_inputs_filtered():
    from claude_history_mcp.server import mcp

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_tool_inputs",
            {"session_id": "sess-tools-abc12345", "tool_name": "Write"},
        )
        assert result.data is not None
        data = result.data
        assert data["count"] >= 1
        assert all(t["tool"] == "Write" for t in data["tool_inputs"])
