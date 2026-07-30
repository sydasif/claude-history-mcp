"""Parse raw JSON dicts into typed models, extract searchable text."""

from __future__ import annotations

from typing import Any

import logging
from pydantic import ValidationError

from .models import (
    SILENT_SKIP_TYPES,
    AiTitleEntry,
    AttachmentEntry,
    BaseEntry,
    PassthroughEntry,
    QueueOperationEntry,
    SummaryEntry,
    SystemEntry,
    TextContent,
    ThinkingContent,
    ToolResultContent,
    ToolUseContent,
    UserEntry,
    AssistantEntry,
)

logger = logging.getLogger(__name__)


def _passthrough(data: dict[str, Any], entry_type: str) -> PassthroughEntry:
    """Build a PassthroughEntry for an unknown/malformed entry with DAG fields."""
    return PassthroughEntry(
        uuid=data["uuid"],
        parentUuid=data.get("parentUuid"),
        sessionId=data["sessionId"],
        timestamp=data.get("timestamp", ""),
        type=entry_type,
        isSidechain=data.get("isSidechain", False),
        agentId=data.get("agentId"),
    )


def create_entry(data: dict[str, Any]) -> Any | None:
    """Parse raw JSON dict into typed model. Returns None for skip types."""
    entry_type = data.get("type", "")
    if entry_type in SILENT_SKIP_TYPES:
        return None

    try:
        if entry_type == "user":
            return UserEntry.model_validate(data)
        elif entry_type == "assistant":
            return AssistantEntry.model_validate(data)
        elif entry_type == "summary":
            return SummaryEntry.model_validate(data)
        elif entry_type == "ai-title":
            return AiTitleEntry.model_validate(data)
        elif entry_type == "system":
            return SystemEntry.model_validate(data)
        elif entry_type == "queue-operation":
            return QueueOperationEntry.model_validate(data)
        elif entry_type == "attachment":
            return AttachmentEntry.model_validate(data)
        elif data.get("uuid") and data.get("sessionId"):
            # Unknown type with DAG fields - keep for searchability
            return _passthrough(data, entry_type)
        return None
    except ValidationError as e:
        # Malformed data - try to create a PassthroughEntry if possible
        logger.debug("Falling back to passthrough for entry type %s: %s", entry_type, e)
        if data.get("uuid") and data.get("sessionId"):
            return _passthrough(data, entry_type)
        # Unknown type with uuid -> keep for searchability
        if data.get("uuid"):
            try:
                return BaseEntry.model_validate(data)
            except Exception:
                return None
        return None


def extract_text(content: list[Any] | None) -> str:
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


def extract_tool_names(content: list[Any] | None) -> list[str]:
    """Extract tool names from content blocks.

    Args:
        content: List of content items.

    Returns:
        List of tool names found in the content.
    """
    if not content:
        return []
    return [item.name for item in content if isinstance(item, ToolUseContent)]


def extract_tool_inputs(content: list[Any] | None) -> list[dict[str, Any]]:
    """Extract tool inputs with file paths and arguments from content blocks.

    Args:
        content: List of content items.

    Returns:
        List of tool input objects with name and input dict.
    """
    if not content:
        return []
    return [
        {"name": item.name, "input": item.input}
        for item in content
        if isinstance(item, ToolUseContent)
    ]


def extract_tool_result_text(content: str | list[dict[str, Any]] | None) -> str:
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


def get_entry_text(entry: Any) -> str:
    """Get searchable text from any entry type.

    Args:
        entry: Any transcript entry type.

    Returns:
        Extracted text content for search indexing.
    """
    # Message-based entries
    msg = getattr(entry, "message", None)
    if msg and hasattr(msg, "content") and msg.content:
        return extract_text(msg.content)

    # System entries
    content = getattr(entry, "content", None)
    if content and isinstance(content, str):
        return content

    # Summary entries
    summary = getattr(entry, "summary", None)
    if summary and isinstance(summary, str):
        return summary

    # AiTitle entries
    ai_title = getattr(entry, "aiTitle", None)
    if ai_title and isinstance(ai_title, str):
        return ai_title

    return ""


def get_entry_tokens(entry: Any) -> tuple[int, int]:
    """Get (input_tokens, output_tokens) from an entry.

    Args:
        entry: Any transcript entry type.

    Returns:
        Tuple of (input_tokens, output_tokens). Returns (0, 0) if no usage info.
    """
    msg = getattr(entry, "message", None)
    usage = getattr(msg, "usage", None) if msg else None
    if usage:
        return (
            getattr(usage, "input_tokens", 0) or 0,
            getattr(usage, "output_tokens", 0) or 0,
        )
    return (0, 0)
