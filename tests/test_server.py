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
        result = await client.call_tool(
            "search_messages", {"query": "hello", "limit": 5}
        )
        assert len(result.data) == 1


@pytest.mark.asyncio
async def test_get_session_stats():
    from claude_history_mcp.server import mcp

    async with Client(mcp) as client:
        sessions = await client.call_tool("list_sessions", {"limit": 1})
        sid = sessions.data[0]["session_id"]
        result = await client.call_tool("get_session_stats", {"session_id": sid})
        # Just verify it returns valid stats structure
        assert "message_count" in result.data
        assert "total_input_tokens" in result.data
        assert "total_output_tokens" in result.data
        assert result.data["message_count"] > 0


@pytest.mark.asyncio
async def test_search_history_empty_is_fine():
    from claude_history_mcp.server import mcp

    async with Client(mcp) as client:
        result = await client.call_tool(
            "search_history", {"query": "model", "limit": 5}
        )
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


@pytest.mark.asyncio
async def test_new_analytics_tools():
    from claude_history_mcp.server import mcp

    async with Client(mcp) as client:
        # Verify tools exist in list_tools
        tools = await client.list_tools()
        tool_names = [t.name for t in tools]
        for expected in [
            "get_cost_estimate",
            "get_usage_trends",
            "get_model_usage",
            "get_tool_usage",
        ]:
            assert expected in tool_names

        # Call them
        res_cost = await client.call_tool("get_cost_estimate", {})
        assert isinstance(res_cost.data, dict)

        res_trends = await client.call_tool("get_usage_trends", {})
        assert isinstance(res_trends.data, list)

        res_models = await client.call_tool("get_model_usage", {})
        assert isinstance(res_models.data, list)

        res_tools = await client.call_tool("get_tool_usage", {})
        assert isinstance(res_tools.data, list)


@pytest.mark.asyncio
async def test_new_tree_and_export_tools():
    from claude_history_mcp.server import mcp

    async with Client(mcp) as client:
        # Verify tools exist
        tools = await client.list_tools()
        tool_names = [t.name for t in tools]
        for expected in [
            "get_project_tree",
            "search_sessions_by_pattern",
            "export_sessions",
            "get_project_stats",
        ]:
            assert expected in tool_names, f"Missing tool: {expected}"

        # Test get_project_tree
        res_tree = await client.call_tool("get_project_tree", {})
        assert isinstance(res_tree.data, list)
        if res_tree.data:
            proj = res_tree.data[0]
            assert "project_path" in proj
            assert "sessions" in proj

        # Test search_sessions_by_pattern
        sessions = await client.call_tool("list_sessions", {"limit": 1})
        sid = sessions.data[0]["session_id"]
        pattern = sid[:8] + "*"
        res_search = await client.call_tool(
            "search_sessions_by_pattern", {"pattern": pattern}
        )
        assert isinstance(res_search.data, list)
        assert len(res_search.data) >= 1

        # Test export_sessions (JSON)
        res_export = await client.call_tool(
            "export_sessions", {"format": "json", "limit": 1}
        )
        assert isinstance(res_export.data, dict)
        assert res_export.data.get("format") == "json"
        assert "data" in res_export.data

        # Test export_sessions (CSV)
        res_export_csv = await client.call_tool(
            "export_sessions", {"format": "csv", "limit": 1}
        )
        assert isinstance(res_export_csv.data, dict)
        assert res_export_csv.data.get("format") == "csv"

        # Test get_project_stats
        projects = await client.call_tool("list_projects", {})
        proj_name = projects.data[0]["display_name"]
        res_stats = await client.call_tool("get_project_stats", {"project": proj_name})
        assert isinstance(res_stats.data, dict)
        assert "project_path" in res_stats.data
        assert "session_count" in res_stats.data
