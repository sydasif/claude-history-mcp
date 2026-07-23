from claude_history_mcp.models import (
    AiTitleEntry,
    AssistantEntry,
    BaseEntry,
    SummaryEntry,
    SystemEntry,
    UserEntry,
)
from claude_history_mcp.parser import (
    create_entry,
    extract_text,
    extract_tool_names,
    extract_tool_result_text,
    get_entry_text,
    get_entry_tokens,
)
from claude_history_mcp.utils import parse_timestamp


def test_create_entry_user():
    assert isinstance(create_entry({"type": "user", "uuid": "u1"}), UserEntry)


def test_create_entry_assistant():
    assert isinstance(create_entry({"type": "assistant", "uuid": "a1"}), AssistantEntry)


def test_create_entry_system():
    assert isinstance(create_entry({"type": "system", "uuid": "s1"}), SystemEntry)


def test_create_entry_summary():
    assert isinstance(create_entry({"type": "summary", "summary": "x"}), SummaryEntry)


def test_create_entry_ai_title():
    assert isinstance(create_entry({"type": "ai-title", "aiTitle": "x"}), AiTitleEntry)


def test_create_entry_skip_file_history_snapshot():
    assert create_entry({"type": "file-history-snapshot"}) is None


def test_create_entry_skip_mode():
    assert create_entry({"type": "mode"}) is None


def test_create_entry_unknown_with_uuid():
    entry = create_entry({"type": "some-future-type", "uuid": "x1"})
    assert isinstance(entry, BaseEntry)


def test_create_entry_unknown_without_uuid():
    assert create_entry({"type": "some-future-type"}) is None


def test_create_entry_malformed_user_falls_back():
    # message is wrong shape entirely -> should fall back to BaseEntry, not raise
    entry = create_entry({"type": "user", "uuid": "u1", "message": "not-a-dict"})
    assert entry is not None


def test_extract_text_mixed_blocks():
    from claude_history_mcp.models import TextContent, ThinkingContent, ToolUseContent

    content = [
        TextContent(text="hello"),
        ThinkingContent(thinking="pondering"),
        ToolUseContent(id="t1", name="Bash", input={}),
    ]
    text = extract_text(content)
    assert "hello" in text
    assert "[thinking]" in text
    assert "[tool: Bash]" in text


def test_extract_text_none():
    assert extract_text(None) == ""


def test_extract_tool_names():
    from claude_history_mcp.models import ToolUseContent

    content = [
        ToolUseContent(id="t1", name="Bash", input={}),
        ToolUseContent(id="t2", name="Read", input={}),
    ]
    assert extract_tool_names(content) == ["Bash", "Read"]


def test_extract_tool_names_empty():
    assert extract_tool_names([]) == []


def test_extract_tool_result_text_string():
    assert extract_tool_result_text("plain result") == "plain result"


def test_extract_tool_result_text_list():
    assert extract_tool_result_text([{"type": "text", "text": "part1"}]) == "part1"


def test_extract_tool_result_text_none():
    assert extract_tool_result_text(None) == ""


def test_get_entry_text_each_type():
    assert get_entry_text(SummaryEntry(summary="s")) == "s"
    assert get_entry_text(AiTitleEntry(aiTitle="t")) == "t"
    assert get_entry_text(SystemEntry(type="system", content="c")) == "c"


def test_get_entry_tokens():
    entry = UserEntry.model_validate(
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": [],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        }
    )
    assert get_entry_tokens(entry) == (10, 5)


def test_get_entry_tokens_no_usage():
    entry = UserEntry.model_validate({"type": "user", "message": {"role": "user", "content": []}})
    assert get_entry_tokens(entry) == (0, 0)


def test_parse_timestamp_valid():
    ts = parse_timestamp("2026-07-23T10:00:00.000Z")
    assert ts is not None
    assert ts.year == 2026


def test_parse_timestamp_none():
    assert parse_timestamp(None) is None


def test_parse_timestamp_invalid():
    assert parse_timestamp("not-a-date") is None


def test_attachment_and_queue_operation_registered():
    """Regression test: spec 2.3 lists `attachment` and `queue-operation` as
    real entry types with dedicated models, but the original blueprint never
    wired them into ENTRY_CREATORS."""
    from claude_history_mcp.models import AttachmentEntry, QueueOperationEntry
    from claude_history_mcp.parser import ENTRY_CREATORS

    assert ENTRY_CREATORS["attachment"] is AttachmentEntry
    assert ENTRY_CREATORS["queue-operation"] is QueueOperationEntry

    entry = create_entry(
        {
            "type": "attachment",
            "uuid": "att1",
            "message": {"role": "user", "content": [{"type": "text", "text": "an attachment"}]},
        }
    )
    assert isinstance(entry, AttachmentEntry)
    assert get_entry_text(entry) == "an attachment"
