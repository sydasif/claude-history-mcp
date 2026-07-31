"""Pydantic models for Claude Code transcript JSON structures.

Local definitions replacing claude-code-log library types. Only the subset
needed by the MCP server is defined here.
"""

from typing import Any, Literal

from pydantic import BaseModel


# =============================================================================
# Content Types (from message.content arrays)
# =============================================================================


class TextContent(BaseModel):
    """Text content block within a message content array."""

    type: Literal["text"]
    text: str


class ImageSource(BaseModel):
    """Base64-encoded image source data."""

    type: Literal["base64"]
    media_type: str
    data: str


class ImageContent(BaseModel):
    """Image content within a content array."""

    type: Literal["image"]
    source: ImageSource


class UsageInfo(BaseModel):
    """Token usage information for tracking API consumption."""

    input_tokens: int | None = None
    output_tokens: int | None = None


class ToolUseContent(BaseModel):
    """Tool invocation content block."""

    type: Literal["tool_use"]
    name: str
    input: dict[str, Any]


class ToolResultContent(BaseModel):
    """Tool result content block."""

    type: Literal["tool_result"]
    content: str | list[dict[str, Any]]
    is_error: bool | None = None


class ThinkingContent(BaseModel):
    """Thinking/reasoning content block."""

    type: Literal["thinking"]
    thinking: str


# Content item types that appear in message content arrays
ContentItem = (
    TextContent | ToolUseContent | ToolResultContent | ThinkingContent | ImageContent
)


# =============================================================================
# Message Models (within transcript entries)
# =============================================================================


class UserMessageModel(BaseModel):
    """User message model."""

    role: Literal["user"]
    content: list[ContentItem]
    usage: UsageInfo | None = None


class AssistantMessageModel(BaseModel):
    """Assistant message model."""

    id: str
    type: Literal["message"]
    role: Literal["assistant"]
    model: str
    content: list[ContentItem]

    usage: UsageInfo | None = None


ToolUseResult = str | list[Any] | dict[str, Any]


# =============================================================================
# Transcript Entry Types
# =============================================================================


class BaseEntry(BaseModel):
    """Base transcript entry with common fields."""

    parentUuid: str | None = None
    isSidechain: bool = False
    cwd: str = ""
    sessionId: str = ""
    uuid: str = ""
    timestamp: str = ""


class UserEntry(BaseEntry):
    """User transcript entry."""

    type: Literal["user"]
    message: UserMessageModel


class AssistantEntry(BaseEntry):
    """Assistant transcript entry."""

    type: Literal["assistant"]
    message: AssistantMessageModel


class SummaryEntry(BaseModel):
    """Summary transcript entry."""

    type: Literal["summary"]
    summary: str
    cwd: str | None = None


class AiTitleEntry(BaseModel):
    """AI-generated session title."""

    type: Literal["ai-title"]
    aiTitle: str


class SystemEntry(BaseEntry):
    """System messages (warnings, notifications, hooks)."""

    type: Literal["system"]
    content: str | None = None


class QueueOperationEntry(BaseModel):
    """Queue operations (enqueue/dequeue/remove)."""

    type: Literal["queue-operation"]

    timestamp: str
    content: list[ContentItem] | str | None = None


class AttachmentEntry(BaseEntry):
    """Out-of-band attachment entry (hook callbacks, etc.)."""

    type: Literal["attachment"]



class PassthroughEntry(BaseModel):
    """Structural-only entry for unknown types with DAG fields."""

    uuid: str
    parentUuid: str | None = None
    sessionId: str
    timestamp: str
    type: str | None = None
    isSidechain: bool = False


# Combined union for transcript entries
TranscriptEntry = (
    UserEntry
    | AssistantEntry
    | SummaryEntry
    | AiTitleEntry
    | SystemEntry
    | QueueOperationEntry
    | AttachmentEntry
    | PassthroughEntry
)


# =============================================================================
# Types to skip during parsing (not needed for search indexing)
# =============================================================================

SILENT_SKIP_TYPES = frozenset(
    {
        "file-history-snapshot",
        "last-prompt",
        "permission-mode",
        "mode",
        "custom-title",
        "agent-name",
        "agent-color",
        "frame-link",
        "file-history-delta",
        "pr-link",
    }
)


# =============================================================================
# MCP Response Models
# =============================================================================


__all__ = [
    # Content types
    "TextContent",
    "ToolUseContent",
    "ToolResultContent",
    "ThinkingContent",
    "ImageContent",
    "UsageInfo",
    # Transcript entry types
    "BaseEntry",
    "UserEntry",
    "AssistantEntry",
    "SystemEntry",
    "SummaryEntry",
    "AiTitleEntry",
    "AttachmentEntry",
    "QueueOperationEntry",
    "PassthroughEntry",
    "TranscriptEntry",
    # Constants
    "SILENT_SKIP_TYPES",
]
