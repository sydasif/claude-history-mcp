"""Pydantic models for Claude Code transcript JSON structures.

Local definitions replacing claude-code-log library types. Only the subset
needed by the MCP server is defined here.
"""

from typing import Any, Literal
from dataclasses import dataclass

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
    cache_creation_input_tokens: int | None = None
    cache_read_input_tokens: int | None = None
    output_tokens: int | None = None
    service_tier: str | None = None
    server_tool_use: dict[str, Any] | None = None


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
    content: str | list[dict[str, Any]]
    is_error: bool | None = None
    agentId: str | None = None


class ThinkingContent(BaseModel):
    """Thinking/reasoning content block."""

    type: Literal["thinking"]
    thinking: str
    signature: str | None = None


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
    stop_reason: str | None = None
    stop_sequence: str | None = None
    usage: UsageInfo | None = None


ToolUseResult = str | list[Any] | dict[str, Any]


# =============================================================================
# Transcript Entry Types
# =============================================================================


class BaseEntry(BaseModel):
    """Base transcript entry with common fields."""

    parentUuid: str | None = None
    isSidechain: bool = False
    userType: str = ""
    cwd: str = ""
    sessionId: str = ""
    version: str = ""
    uuid: str = ""
    timestamp: str = ""
    isMeta: bool | None = None
    agentId: str | None = None
    gitBranch: str | None = None
    teamName: str | None = None
    spawnedAgentId: str | None = None


class UserEntry(BaseEntry):
    """User transcript entry."""

    type: Literal["user"]
    message: UserMessageModel
    toolUseResult: ToolUseResult | None = None
    sourceToolUseID: str | None = None


class AssistantEntry(BaseEntry):
    """Assistant transcript entry."""

    type: Literal["assistant"]
    message: AssistantMessageModel
    requestId: str | None = None


class SummaryEntry(BaseModel):
    """Summary transcript entry."""

    type: Literal["summary"]
    summary: str
    leafUuid: str
    cwd: str | None = None
    sessionId: str | None = None


class AiTitleEntry(BaseModel):
    """AI-generated session title."""

    type: Literal["ai-title"]
    aiTitle: str
    sessionId: str


class SystemEntry(BaseEntry):
    """System messages (warnings, notifications, hooks)."""

    type: Literal["system"]
    content: str | None = None
    subtype: str | None = None
    level: str | None = None
    hasOutput: bool | None = None
    hookErrors: list[str] | None = None
    hookInfos: list[dict[str, Any]] | None = None
    preventedContinuation: bool | None = None
    compactMetadata: dict[str, Any] | None = None


class QueueOperationEntry(BaseModel):
    """Queue operations (enqueue/dequeue/remove)."""

    type: Literal["queue-operation"]
    operation: Literal["enqueue", "dequeue", "remove", "popAll"]
    timestamp: str
    sessionId: str
    content: list[ContentItem] | str | None = None


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
    parentUuid: str | None = None
    sessionId: str
    timestamp: str
    type: str | None = None
    isSidechain: bool = False
    agentId: str | None = None


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
    # Memory
    "MemoryNote",
]


@dataclass
class MemoryNote:
    """Project memory note with decay engine metadata."""

    note_id: str
    project: str
    statement: str
    description: str
    note_type: str  # observation | world | experience | decision | bug
    session_ids: list[str]
    related: list[str]
    created_at: str  # ISO timestamp
    # Decay engine fields
    is_foundational: bool = False
    stability: float = 8.0
    recall_count: int = 1
    last_recalled_turn: int = 0
    evicted: bool = False
    evicted_at_turn: int | None = None
