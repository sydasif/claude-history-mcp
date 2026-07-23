"""Parse raw JSON dicts into typed transcript entry models, extract searchable text."""

from typing import Any

from pydantic import BaseModel

from .models import (
    SILENT_SKIP_TYPES,
    AiTitleEntry,
    AssistantEntry,
    AttachmentEntry,
    BaseEntry,
    ContentItem,
    QueueOperationEntry,
    SummaryEntry,
    SystemEntry,
    TextContent,
    ThinkingContent,
    ToolResultContent,
    ToolUseContent,
    TranscriptEntry,
    UserEntry,
)

ENTRY_CREATORS: dict[str, type[BaseModel]] = {
    "user": UserEntry,
    "assistant": AssistantEntry,
    "system": SystemEntry,
    "summary": SummaryEntry,
    "ai-title": AiTitleEntry,
    "attachment": AttachmentEntry,
    "queue-operation": QueueOperationEntry,
}


def create_entry(data: dict[str, Any]) -> TranscriptEntry | None:
    """Parse raw JSON dict into typed model. Returns None for skip types."""
    entry_type = data.get("type", "")
    if entry_type in SILENT_SKIP_TYPES:
        return None
    model_class = ENTRY_CREATORS.get(entry_type)
    if model_class:
        try:
            return model_class.model_validate(data)
        except Exception:
            # Fallback: try BaseEntry for malformed specialized entries
            try:
                return BaseEntry.model_validate(data)
            except Exception:
                return None
    # Unknown type with uuid → keep for searchability
    if data.get("uuid"):
        try:
            return BaseEntry.model_validate(data)
        except Exception:
            return None
    return None


def extract_text(content: "list[ContentItem] | None") -> str:
    """Extract all text content from a message's content blocks."""
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


def extract_tool_names(content: "list[ContentItem] | None") -> list[str]:
    """Extract tool names from content blocks."""
    if not content:
        return []
    return [item.name for item in content if isinstance(item, ToolUseContent)]


def extract_tool_result_text(content: "str | list[dict[str, Any]] | None") -> str:
    """Normalize tool_result content to a string."""
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


def get_entry_text(entry: TranscriptEntry) -> str:
    """Get searchable text from any entry type."""
    if (
        isinstance(entry, (UserEntry, AssistantEntry, AttachmentEntry, QueueOperationEntry))
        and entry.message
    ):
        return extract_text(entry.message.content)
    if isinstance(entry, SystemEntry):
        return entry.content or ""
    if isinstance(entry, SummaryEntry):
        return entry.summary
    if isinstance(entry, AiTitleEntry):
        return entry.aiTitle
    return ""


def get_entry_tokens(entry: TranscriptEntry) -> tuple[int, int]:
    """Get (input_tokens, output_tokens) from an entry."""
    msg = None
    if isinstance(entry, (UserEntry, AssistantEntry, AttachmentEntry, QueueOperationEntry)):
        msg = entry.message
    if msg and msg.usage:
        return (msg.usage.input_tokens or 0, msg.usage.output_tokens or 0)
    return (0, 0)
