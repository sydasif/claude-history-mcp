"""Pydantic models for Claude Code transcript JSON structures.

Local definitions replacing claude-code-log library types. Only the subset
needed by the MCP server is defined here.
"""

from typing import Any, Literal, Optional, Union

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

    input_tokens: Optional[int] = None
    cache_creation_input_tokens: Optional[int] = None
    cache_read_input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    service_tier: Optional[str] = None
    server_tool_use: Optional[dict[str, Any]] = None


class ToolUseContent(BaseModel):
    """Tool invocation content block."""

    type: Literal["tool_use"]
    id: str
    name: str
    input: dict[str, Any]


class ToolResultContent(BaseModel):
    """Tool result content block."""

    type: Literal["tool_result"]
    tool_use_id: str
    content: Union[str, list[dict[str, Any]]]
    is_error: Optional[bool] = None
    agentId: Optional[str] = None


class ThinkingContent(BaseModel):
    """Thinking/reasoning content block."""

    type: Literal["thinking"]
    thinking: str
    signature: Optional[str] = None


# Content item types that appear in message content arrays
ContentItem = Union[
    TextContent,
    ToolUseContent,
    ToolResultContent,
    ThinkingContent,
    ImageContent,
]


# =============================================================================
# Message Models (within transcript entries)
# =============================================================================


class UserMessageModel(BaseModel):
    """User message model."""

    role: Literal["user"]
    content: list[ContentItem]
    usage: Optional[UsageInfo] = None


class AssistantMessageModel(BaseModel):
    """Assistant message model."""

    id: str
    type: Literal["message"]
    role: Literal["assistant"]
    model: str
    content: list[ContentItem]
    stop_reason: Optional[str] = None
    stop_sequence: Optional[str] = None
    usage: Optional[UsageInfo] = None


ToolUseResult = Union[
    str,
    list[Any],
    dict[str, Any],
]


# =============================================================================
# Transcript Entry Types
# =============================================================================


class BaseEntry(BaseModel):
    """Base transcript entry with common fields."""

    parentUuid: Optional[str] = None
    isSidechain: bool = False
    userType: str = ""
    cwd: str = ""
    sessionId: str = ""
    version: str = ""
    uuid: str = ""
    timestamp: str = ""
    isMeta: Optional[bool] = None
    agentId: Optional[str] = None
    gitBranch: Optional[str] = None
    teamName: Optional[str] = None
    spawnedAgentId: Optional[str] = None


class UserEntry(BaseEntry):
    """User transcript entry."""

    type: Literal["user"]
    message: UserMessageModel
    toolUseResult: Optional[ToolUseResult] = None
    sourceToolUseID: Optional[str] = None


class AssistantEntry(BaseEntry):
    """Assistant transcript entry."""

    type: Literal["assistant"]
    message: AssistantMessageModel
    requestId: Optional[str] = None


class SummaryEntry(BaseModel):
    """Summary transcript entry."""

    type: Literal["summary"]
    summary: str
    leafUuid: str
    cwd: Optional[str] = None
    sessionId: Optional[str] = None


class AiTitleEntry(BaseModel):
    """AI-generated session title."""

    type: Literal["ai-title"]
    aiTitle: str
    sessionId: str


class SystemEntry(BaseEntry):
    """System messages (warnings, notifications, hooks)."""

    type: Literal["system"]
    content: Optional[str] = None
    subtype: Optional[str] = None
    level: Optional[str] = None
    hasOutput: Optional[bool] = None
    hookErrors: Optional[list[str]] = None
    hookInfos: Optional[list[dict[str, Any]]] = None
    preventedContinuation: Optional[bool] = None
    compactMetadata: Optional[dict[str, Any]] = None


class QueueOperationEntry(BaseModel):
    """Queue operations (enqueue/dequeue/remove)."""

    type: Literal["queue-operation"]
    operation: Literal["enqueue", "dequeue", "remove", "popAll"]
    timestamp: str
    sessionId: str
    content: Optional[Union[list[ContentItem], str]] = None


class AttachmentEntry(BaseEntry):
    """Out-of-band attachment entry (hook callbacks, etc.)."""

    type: Literal["attachment"]
    attachment: dict[str, Any] = {}
    userType: str = "external"
    cwd: str = ""
    version: str = ""


class PassthroughEntry(BaseModel):
    """Structural-only entry for unknown types with DAG fields."""

    uuid: str
    parentUuid: Optional[str] = None
    sessionId: str
    timestamp: str
    type: Optional[str] = None
    isSidechain: bool = False
    agentId: Optional[str] = None


# Combined union for transcript entries
TranscriptEntry = Union[
    UserEntry,
    AssistantEntry,
    SummaryEntry,
    AiTitleEntry,
    SystemEntry,
    QueueOperationEntry,
    AttachmentEntry,
    PassthroughEntry,
]


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
    }
)


# =============================================================================
# MCP Response Models
# =============================================================================


class HistoryCommand(BaseModel):
    """History command entry from history.jsonl."""

    display: str
    pastedContents: dict[str, Any] = {}
    timestamp: int  # epoch milliseconds
    project: str
    sessionId: str


class SessionSummary(BaseModel):
    """Summary of a session for listing purposes."""

    session_id: str
    project: str
    summary: str | None = None
    ai_title: str | None = None
    first_user_message: str | None = None
    message_count: int = 0
    first_timestamp: str | None = None
    last_timestamp: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cwd: str | None = None


class ProjectInfo(BaseModel):
    """Project metadata."""

    project_path: str
    display_name: str
    session_count: int
    message_count: int
    earliest_timestamp: str | None = None
    latest_timestamp: str | None = None
    total_input_tokens: int = 0
    total_output_tokens: int = 0


class MessageResult(BaseModel):
    """Single message in search results."""

    session_id: str
    project: str
    timestamp: str | None = None
    role: str
    text_preview: str
    tool_names: list[str] = []
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0


class SessionStats(BaseModel):
    """Session statistics."""

    session_id: str
    duration_minutes: float | None = None
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    message_count: int = 0
    tool_usage: dict[str, int] = {}
    models_used: list[str] = []
    error_count: int = 0


class SessionTranscript(BaseModel):
    """Full session transcript."""

    session_id: str
    project: str
    summary: str | None = None
    messages: list[dict[str, Any]] = []


class RecentActivityEntry(BaseModel):
    """Recent activity entry."""

    session_id: str
    project: str
    timestamp: str
    role: str
    text_preview: str


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
    # MCP response models
    "HistoryCommand",
    "SessionSummary",
    "ProjectInfo",
    "MessageResult",
    "SessionStats",
    "SessionTranscript",
    "RecentActivityEntry",
]
