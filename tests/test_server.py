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
                    "cwd": "/tmp/demo",
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
                        "usage": {"input_tokens": 5, "output_tokens": 5},
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
async def test_list_projects():
    from claude_history_mcp.server import mcp

    async with Client(mcp) as client:
        result = await client.call_tool("list_projects", {})
        assert isinstance(result.data, list)
        assert len(result.data) == 1


@pytest.mark.asyncio
async def test_list_sessions():
    from claude_history_mcp.server import mcp

    async with Client(mcp) as client:
        result = await client.call_tool("list_sessions", {"limit": 5})
        assert len(result.data) == 1


@pytest.mark.asyncio
async def test_search_messages():
    from claude_history_mcp.server import mcp

    async with Client(mcp) as client:
        result = await client.call_tool("search_messages", {"query": "hello", "limit": 5})
        assert len(result.data) == 1


@pytest.mark.asyncio
async def test_get_session_stats():
    from claude_history_mcp.server import mcp

    async with Client(mcp) as client:
        sessions = await client.call_tool("list_sessions", {"limit": 1})
        sid = sessions.data[0]["session_id"]
        result = await client.call_tool("get_session_stats", {"session_id": sid})
        assert result.data["message_count"] == 2


@pytest.mark.asyncio
async def test_search_history_empty_is_fine():
    from claude_history_mcp.server import mcp

    async with Client(mcp) as client:
        result = await client.call_tool("search_history", {"query": "model", "limit": 5})
        assert isinstance(result.data, list)


@pytest.mark.asyncio
async def test_get_recent_activity():
    from claude_history_mcp.server import mcp

    async with Client(mcp) as client:
        result = await client.call_tool("get_recent_activity", {"hours": 48})
        assert isinstance(result.data, list)


@pytest.mark.asyncio
async def test_server_has_expected_tools():
    from claude_history_mcp.server import mcp

    async with Client(mcp) as client:
        tools = await client.list_tools()
        tool_names = [t.name for t in tools]
        expected = [
            "list_projects",
            "list_sessions",
            "search_messages",
            "get_session",
            "get_session_stats",
            "search_history",
            "get_recent_activity",
        ]
        for name in expected:
            assert name in tool_names, f"Missing tool: {name}"


@pytest.mark.asyncio
async def test_server_has_expected_resources():
    from claude_history_mcp.server import mcp

    async with Client(mcp) as client:
        resources = await client.list_resources()
        resource_uris = [str(r.uri) for r in resources]
        assert "claude://projects" in resource_uris
        assert "claude://history" in resource_uris
