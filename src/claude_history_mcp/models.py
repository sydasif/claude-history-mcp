"""MCP-specific models built on top of claude-code-log library types.

This module re-exports library types and adds MCP-specific response models.
"""

from typing import Any
from pydantic import BaseModel

from claude_code_log.models import (
    UserTranscriptEntry as UserEntry,
    AssistantTranscriptEntry as AssistantEntry,
    SystemTranscriptEntry as SystemEntry,
    SummaryTranscriptEntry as SummaryEntry,
    AiTitleTranscriptEntry as AiTitleEntry,
    AttachmentTranscriptEntry as AttachmentEntry,
    QueueOperationTranscriptEntry as QueueOperationEntry,
    BaseTranscriptEntry as BaseEntry,
    TranscriptEntry,
    TextContent,
    ToolUseContent,
    ToolResultContent,
    ThinkingContent,
    ImageContent,
    UsageInfo,
)

# Re-export library types for backward compatibility
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

# MCP Response Models (new - not in library)


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


# Combined union for transcript entry (for backward compatibility)
# TranscriptEntry is already imported from claude_code_log.models


__all__ = [
    # Library types (re-exported)
    "TranscriptEntry",
    "UserEntry",
    "AssistantEntry",
    "SystemEntry",
    "SummaryEntry",
    "AiTitleEntry",
    "AttachmentEntry",
    "QueueOperationEntry",
    "BaseEntry",
    "TextContent",
    "ToolUseContent",
    "ToolResultContent",
    "ThinkingContent",
    "ImageContent",
    "UsageInfo",
    "SILENT_SKIP_TYPES",
    # MCP-specific models
    "HistoryCommand",
    "SessionSummary",
    "ProjectInfo",
    "MessageResult",
    "SessionStats",
    "SessionTranscript",
    "RecentActivityEntry",
]