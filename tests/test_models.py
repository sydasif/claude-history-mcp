"""Tests for local Pydantic models."""

from typing import Any, cast

from claude_history_mcp.models import (
    AiTitleEntry,
    PassthroughEntry,
    SummaryEntry,
    SystemEntry,
    TextContent,
    ThinkingContent,
    ToolResultContent,
    ToolUseContent,
    UserEntry,
    AssistantEntry,
    SILENT_SKIP_TYPES,
    HistoryCommand,
)


def test_text_content():
    c = TextContent.model_validate({"type": "text", "text": "hi"})
    assert c.text == "hi"


def test_tool_use_content():
    c = ToolUseContent.model_validate(
        {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"cmd": "ls"}}
    )
    assert c.name == "Bash"


def test_tool_result_content_string():
    c = ToolResultContent.model_validate(
        {"type": "tool_result", "tool_use_id": "t1", "content": "ok"}
    )
    assert c.content == "ok"


def test_tool_result_content_list():
    c = ToolResultContent.model_validate(
        {
            "type": "tool_result",
            "tool_use_id": "t1",
            "content": [{"type": "text", "text": "ok"}],
        }
    )
    assert isinstance(c.content, list)


def test_user_entry_mixed_content():
    entry = UserEntry(
        type="user",
        uuid="u1",
        sessionId="s1",
        parentUuid=None,
        isSidechain=False,
        userType="external",
        cwd="/tmp",
        version="1.0",
        timestamp="2024-01-01T00:00:00Z",
        message=cast(
            Any,
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "hello"},
                    {"type": "tool_result", "tool_use_id": "t1", "content": "done"},
                ],
                "usage": None,
            },
        ),
    )
    assert len(entry.message.content) == 2


def test_assistant_entry_thinking_text_tool_use():
    entry = AssistantEntry(
        type="assistant",
        uuid="a1",
        sessionId="s1",
        parentUuid=None,
        isSidechain=False,
        userType="external",
        cwd="/tmp",
        version="1.0",
        timestamp="2024-01-01T00:00:00Z",
        message=cast(
            Any,
            {
                "id": "msg-1",
                "type": "message",
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "let me think"},
                    {"type": "text", "text": "here's the answer"},
                    {"type": "tool_use", "id": "t1", "name": "Read", "input": {}},
                ],
                "model": "claude-3",
                "usage": None,
            },
        ),
    )
    assert len(entry.message.content) == 3


def test_system_entry_subtype():
    entry = SystemEntry(
        type="system",
        subtype="stop_hook_summary",
        content="done",
        uuid="u1",
        sessionId="s1",
        parentUuid=None,
        isSidechain=False,
        userType="external",
        cwd="/tmp",
        version="1.0",
        timestamp="2024-01-01T00:00:00Z",
    )
    assert entry.subtype == "stop_hook_summary"


def test_summary_entry():
    entry = SummaryEntry(type="summary", summary="a session about X", leafUuid="leaf-1")
    assert entry.summary == "a session about X"


def test_ai_title_entry():
    entry = AiTitleEntry(type="ai-title", aiTitle="Fixing the parser", sessionId="s1")
    assert entry.aiTitle == "Fixing the parser"


def test_silent_skip_types_contents():
    assert "file-history-snapshot" in SILENT_SKIP_TYPES
    assert "mode" in SILENT_SKIP_TYPES
    assert "user" not in SILENT_SKIP_TYPES


def test_content_item_discriminated_union():
    entry = UserEntry(
        type="user",
        uuid="u1",
        sessionId="s1",
        parentUuid=None,
        isSidechain=False,
        userType="external",
        cwd="/tmp",
        version="1.0",
        timestamp="2024-01-01T00:00:00Z",
        message=cast(
            Any,
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "t"},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": "...",
                        },
                    },
                ],
                "usage": None,
            },
        ),
    )
    assert len(entry.message.content) == 2
    types = {type(c).__name__ for c in entry.message.content}
    assert types == {"TextContent", "ImageContent"}


def test_history_command_from_dict():
    hc = HistoryCommand.model_validate(
        {
            "display": "ls -la",
            "pastedContents": {},
            "timestamp": 1784532628943,
            "project": "/home/zulu/litellm-proxy",
            "sessionId": "a7431e9a-48bb-44c9-b2cf-84121bf94917",
        }
    )
    assert hc.timestamp == 1784532628943


def test_user_entry_missing_message_no_crash():
    entry = UserEntry(
        type="user",
        uuid="u1",
        sessionId="s1",
        parentUuid=None,
        isSidechain=False,
        userType="external",
        cwd="/tmp",
        version="1.0",
        timestamp="2024-01-01T00:00:00Z",
        message=cast(Any, {"role": "user", "content": [], "usage": None}),
    )
    assert entry is not None


def test_assistant_entry_error_true():
    entry = AssistantEntry(
        type="assistant",
        uuid="a1",
        sessionId="s1",
        parentUuid=None,
        isSidechain=False,
        userType="external",
        cwd="/tmp",
        version="1.0",
        timestamp="2024-01-01T00:00:00Z",
        message=cast(
            Any,
            {
                "id": "msg-1",
                "type": "message",
                "role": "assistant",
                "content": [],
                "model": "claude-3",
                "usage": None,
            },
        ),
        requestId="req-1",
    )
    assert entry.requestId == "req-1"


def test_thinking_content_signature_optional():
    c = ThinkingContent(type="thinking", thinking="hmm")
    assert c.signature is None


def test_passthrough_entry():
    entry = PassthroughEntry(
        uuid="p1",
        sessionId="s1",
        timestamp="2024-01-01T00:00:00Z",
        type="unknown-type",
    )
    assert entry.uuid == "p1"
    assert entry.type == "unknown-type"
