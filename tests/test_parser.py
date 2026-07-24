"""Tests for parser using claude-code-log library models."""

from claude_code_log.api import create_transcript_entry
from claude_code_log.models import (
    UserTranscriptEntry as UserEntry,
    AssistantTranscriptEntry as AssistantEntry,
    SystemTranscriptEntry as SystemEntry,
    SummaryTranscriptEntry as SummaryEntry,
    AiTitleTranscriptEntry as AiTitleEntry,
    AttachmentTranscriptEntry as AttachmentEntry,
    QueueOperationTranscriptEntry as QueueOperationEntry,
    BaseTranscriptEntry as BaseEntry,
    TextContent,
    ToolUseContent,
    ToolResultContent,
    ThinkingContent,
    ImageContent,
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
    entry = create_entry({
        "type": "user",
        "uuid": "u1",
        "sessionId": "s1",
        "parentUuid": None,
        "isSidechain": False,
        "userType": "external",
        "cwd": "/tmp",
        "version": "1.0",
        "timestamp": "2024-01-01T00:00:00Z",
        "message": {"role": "user", "content": [], "usage": None}
    })
    assert isinstance(entry, UserEntry)


def test_create_entry_assistant():
    entry = create_entry({
        "type": "assistant",
        "uuid": "a1",
        "sessionId": "s1",
        "parentUuid": None,
        "isSidechain": False,
        "userType": "external",
        "cwd": "/tmp",
        "version": "1.0",
        "timestamp": "2024-01-01T00:00:00Z",
        "message": {"id": "msg-1", "type": "message", "role": "assistant", "content": [], "model": "claude-3", "usage": None},
        "requestId": "req-1"
    })
    assert isinstance(entry, AssistantEntry)


def test_create_entry_system():
    entry = create_entry({
        "type": "system",
        "uuid": "s1",
        "sessionId": "s1",
        "parentUuid": None,
        "isSidechain": False,
        "userType": "external",
        "cwd": "/tmp",
        "version": "1.0",
        "timestamp": "2024-01-01T00:00:00Z",
        "content": "system message",
    })
    assert isinstance(entry, SystemEntry)


def test_create_entry_summary():
    entry = create_entry({
        "type": "summary",
        "summary": "x",
        "leafUuid": "leaf-1",
    })
    assert isinstance(entry, SummaryEntry)


def test_create_entry_ai_title():
    entry = create_entry({
        "type": "ai-title",
        "aiTitle": "x",
        "sessionId": "s1",
    })
    assert isinstance(entry, AiTitleEntry)


def test_create_entry_skip_file_history_snapshot():
    entry = create_entry({
        "type": "file-history-snapshot",
    })
    assert entry is None


def test_create_entry_skip_mode():
    entry = create_entry({
        "type": "mode",
    })
    assert entry is None


def test_create_entry_unknown_with_uuid():
    entry = create_entry({
        "type": "some-future-type",
        "uuid": "x1",
        "sessionId": "s1",
        "parentUuid": None,
        "isSidechain": False,
    })
    # Unknown types with uuid become PassthroughTranscriptEntry from library
    from claude_code_log.models import PassthroughTranscriptEntry
    assert isinstance(entry, PassthroughTranscriptEntry)


def test_create_entry_unknown_without_uuid():
    entry = create_entry({
        "type": "some-future-type",
    })
    assert entry is None


def test_create_entry_malformed_user_falls_back():
    # message is wrong shape entirely -> should fall back to PassthroughTranscriptEntry, not raise
    entry = create_entry({"type": "user", "uuid": "u1", "sessionId": "s1", "message": "not-a-dict"})
    from claude_code_log.models import PassthroughTranscriptEntry
    assert entry is not None
    assert isinstance(entry, PassthroughTranscriptEntry)


def test_extract_text_mixed_blocks():
    content = [
        TextContent(type="text", text="hello"),
        ThinkingContent(type="thinking", thinking="pondering"),
        ToolUseContent(type="tool_use", id="t1", name="Bash", input={}),
    ]
    text = extract_text(content)
    assert "hello" in text
    assert "[thinking]" in text
    assert "[tool: Bash]" in text


def test_extract_text_none():
    assert extract_text(None) == ""


def test_extract_tool_names():
    content = [
        ToolUseContent(type="tool_use", id="t1", name="Bash", input={}),
        ToolUseContent(type="tool_use", id="t2", name="Read", input={}),
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
    # Summary entry
    entry = SummaryEntry(type="summary", summary="s", leafUuid="leaf-1")
    assert get_entry_text(entry) == "s"

    # AiTitle entry
    entry = AiTitleEntry(type="ai-title", aiTitle="t", sessionId="s1")
    assert get_entry_text(entry) == "t"

    # System entry
    entry = SystemEntry(
        type="system", content="c",
        uuid="u1", sessionId="s1", parentUuid=None,
        isSidechain=False, userType="external", cwd="/tmp",
        version="1.0", timestamp="2024-01-01T00:00:00Z"
    )
    assert get_entry_text(entry) == "c"


def test_get_entry_tokens():
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
        message={
            "role": "user",
            "content": [],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
    )
    assert get_entry_tokens(entry) == (10, 5)


def test_get_entry_tokens_no_usage():
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
        message={"role": "user", "content": []}
    )
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
    real entry types that must be parseable by create_entry."""
    from claude_code_log.models import AttachmentTranscriptEntry, QueueOperationTranscriptEntry

    attachment = create_entry(
        {
            "type": "attachment",
            "uuid": "att1",
            "sessionId": "s1",
            "parentUuid": None,
            "isSidechain": False,
            "userType": "external",
            "cwd": "/tmp",
            "version": "1.0",
            "timestamp": "2024-01-01T00:00:00Z",
            "message": {"role": "user", "content": [{"type": "text", "text": "an attachment"}], "usage": None},
        }
    )
    assert isinstance(attachment, AttachmentTranscriptEntry)