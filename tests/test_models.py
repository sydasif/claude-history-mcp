from claude_history_mcp.models import (
    AiTitleEntry,
    AssistantEntry,
    HistoryCommand,
    SILENT_SKIP_TYPES,
    SummaryEntry,
    SystemEntry,
    TextContent,
    ThinkingContent,
    ToolResultContent,
    ToolUseContent,
    UserEntry,
)


def test_text_content():
    c = TextContent.model_validate({"type": "text", "text": "hi"})
    assert c.text == "hi"


def test_tool_use_content():
    c = ToolUseContent.model_validate({"type": "tool_use", "id": "t1", "name": "Bash", "input": {"cmd": "ls"}})
    assert c.name == "Bash"


def test_tool_result_content_string():
    c = ToolResultContent.model_validate({"type": "tool_result", "tool_use_id": "t1", "content": "ok"})
    assert c.content == "ok"


def test_tool_result_content_list():
    c = ToolResultContent.model_validate(
        {"type": "tool_result", "tool_use_id": "t1", "content": [{"type": "text", "text": "ok"}]}
    )
    assert isinstance(c.content, list)


def test_user_entry_mixed_content():
    entry = UserEntry.model_validate(
        {
            "type": "user",
            "uuid": "u1",
            "message": {
                "role": "user",
                "content": [
                    {"type": "text", "text": "hello"},
                    {"type": "tool_result", "tool_use_id": "t1", "content": "done"},
                ],
            },
        }
    )
    assert len(entry.message.content) == 2


def test_assistant_entry_thinking_text_tool_use():
    entry = AssistantEntry.model_validate(
        {
            "type": "assistant",
            "uuid": "a1",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "let me think"},
                    {"type": "text", "text": "here's the answer"},
                    {"type": "tool_use", "id": "t1", "name": "Read", "input": {}},
                ],
            },
        }
    )
    assert len(entry.message.content) == 3


def test_system_entry_subtype():
    entry = SystemEntry.model_validate({"type": "system", "subtype": "stop_hook_summary", "content": "done"})
    assert entry.subtype == "stop_hook_summary"


def test_summary_entry():
    entry = SummaryEntry.model_validate({"type": "summary", "summary": "a session about X"})
    assert entry.summary == "a session about X"


def test_ai_title_entry():
    entry = AiTitleEntry.model_validate({"type": "ai-title", "aiTitle": "Fixing the parser"})
    assert entry.aiTitle == "Fixing the parser"


def test_silent_skip_types_contents():
    assert "file-history-snapshot" in SILENT_SKIP_TYPES
    assert "mode" in SILENT_SKIP_TYPES
    assert "user" not in SILENT_SKIP_TYPES


def test_content_item_discriminated_union():
    entry = UserEntry.model_validate(
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": [
                    {"type": "text", "text": "t"},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "..."}},
                ],
            },
        }
    )
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
    entry = UserEntry.model_validate({"type": "user", "uuid": "u1"})
    assert entry.message is None


def test_assistant_entry_error_true():
    entry = AssistantEntry.model_validate({"type": "assistant", "uuid": "a1", "error": True})
    assert entry.error is True


def test_thinking_content_signature_optional():
    c = ThinkingContent.model_validate({"type": "thinking", "thinking": "hmm"})
    assert c.signature is None
