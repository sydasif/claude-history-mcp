"""Parse raw JSON dicts using claude-code-log library, extract searchable text."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime

from claude_code_log.api import (
    create_transcript_entry,
    parse_timestamp as lib_parse_timestamp,
)

from claude_code_log.models import (
    TextContent,
    ThinkingContent,
    ToolUseContent,
    ToolResultContent,
)

from .models import (
    SILENT_SKIP_TYPES,
    BaseEntry,
    UserEntry,
    AssistantEntry,
    SystemEntry,
    SummaryEntry,
    AiTitleEntry,
    AttachmentEntry,
    QueueOperationEntry,
)


def create_entry(data: dict[str, Any]) -> BaseEntry | None:
    """Parse raw JSON dict into typed model. Returns None for skip types."""
    entry_type = data.get("type", "")
    if entry_type in SILENT_SKIP_TYPES:
        return None

    # Use library's create_transcript_entry for proper validation
    try:
        return create_transcript_entry(data)
    except Exception:
        # Malformed data - create a PassthroughTranscriptEntry to keep it searchable
        if data.get("uuid") and data.get("sessionId"):
            from claude_code_log.models import PassthroughTranscriptEntry
            return PassthroughTranscriptEntry(
                uuid=data["uuid"],
                parentUuid=data.get("parentUuid"),
                sessionId=data["sessionId"],
                timestamp=data.get("timestamp", ""),
                type=entry_type,
                isSidechain=data.get("isSidechain", False),
                agentId=data.get("agentId"),
            )
        # Unknown type with uuid -> keep for searchability
        if data.get("uuid"):
            try:
                return BaseEntry.model_validate(data)
            except Exception:
                return None
        return None


def extract_text(content: "list[Any] | None") -> str:
    """Extract all text content from a message's content blocks, including thinking and tool info.

    Args:
        content: List of content items (TextContent, ThinkingContent, ToolUseContent, ToolResultContent).

    Returns:
        Concatenated text from all content blocks, with thinking and tool markers.
    """
    if not content:
        return ""
    parts = []
    for item in content:
        if isinstance(item, TextContent):
            parts.append(item.text)
        elif isinstance(item, ThinkingContent):
            parts.append(f"[thinking] {item.thinking[:500]}")
        elif isinstance(item, ToolUseContent):
            parts.append(f"[tool: {item.name}]")
        elif isinstance(item, ToolResultContent):
            parts.append(f"[tool_result] {extract_tool_result_text(item.content)}")
    return "\n".join(parts)


def extract_tool_names(content: "list[Any] | None") -> list[str]:
    """Extract tool names from content blocks.

    Args:
        content: List of content items.

    Returns:
        List of tool names found in the content.
    """
    if not content:
        return []
    return [item.name for item in content if isinstance(item, ToolUseContent)]


def extract_tool_result_text(content: "str | list[dict[str, Any]] | None") -> str:
    """Normalize tool_result content to a string.

    Args:
        content: Tool result content - either a string or list of content blocks.

    Returns:
        Normalized string representation of the tool result.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(block.get("text", ""))
        return "\n".join(texts)
    return str(content)


def get_entry_text(entry: BaseEntry) -> str:
    """Get searchable text from any entry type.

    Args:
        entry: Any transcript entry type.

    Returns:
        Extracted text content for search indexing.
    """
    # Message-based entries
    if hasattr(entry, "message") and entry.message:
        return extract_text(entry.message.content)

    # System entries
    if hasattr(entry, "content") and entry.content:
        return entry.content

    # Summary entries
    if hasattr(entry, "summary") and entry.summary:
        return entry.summary

    # AiTitle entries
    if hasattr(entry, "aiTitle") and entry.aiTitle:
        return entry.aiTitle

    return ""


def get_entry_tokens(entry: BaseEntry) -> tuple[int, int]:
    """Get (input_tokens, output_tokens) from an entry.

    Args:
        entry: Any transcript entry type.

    Returns:
        Tuple of (input_tokens, output_tokens). Returns (0, 0) if no usage info.
    """
    if hasattr(entry, "message") and entry.message and entry.message.usage:
        usage = entry.message.usage
        return (usage.input_tokens or 0, usage.output_tokens or 0)
    return (0, 0)


def parse_timestamp(ts: str | None) -> datetime | None:
    """Parse ISO 8601 timestamp to datetime. Returns None for missing/invalid.

    Args:
        ts: ISO 8601 timestamp string (with or without Z suffix).

    Returns:
        Naive UTC datetime for consistent comparison, or None if missing/invalid.
    """
    return lib_parse_timestamp(ts)