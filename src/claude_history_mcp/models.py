"""Pydantic models for Claude Code JSONL transcript entries and content blocks."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Content block types
# ---------------------------------------------------------------------------


class TextContent(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["text"] = "text"
    text: str


class ToolUseContent(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    input: dict[str, Any] = {}


class ToolResultContent(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: str | list[dict[str, Any]] = ""
    is_error: bool | None = None


class ThinkingContent(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["thinking"] = "thinking"
    thinking: str
    signature: str | None = None


class ImageContent(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["image"] = "image"
    source: dict[str, Any] = {}


ContentItem = Annotated[
    TextContent | ToolUseContent | ToolResultContent | ThinkingContent | ImageContent,
    Field(discriminator="type"),
]

# ---------------------------------------------------------------------------
# Usage / message
# ---------------------------------------------------------------------------


class UsageInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_creation_input_tokens: int | None = None
    cache_read_input_tokens: int | None = None
    server_tool_use: dict[str, Any] | None = None
    service_tier: str | None = None


class MessageModel(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: str
    content: list[ContentItem] = []
    model: str | None = None
    usage: UsageInfo | None = None
    id: str | None = None


# ---------------------------------------------------------------------------
# Entry types
# ---------------------------------------------------------------------------

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


class BaseEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    uuid: str | None = None
    parentUuid: str | None = None
    sessionId: str | None = None
    session_id: str | None = None  # snake_case fallback seen in some entries
    timestamp: str | None = None
    type: str
    isSidechain: bool = False
    userType: str = ""
    cwd: str | None = None
    version: str | None = None
    gitBranch: str | None = None
    isMeta: bool | None = None
    agentId: str | None = None
    spawnedAgentId: str | None = None
    teamName: str | None = None

    @property
    def resolved_session_id(self) -> str | None:
        """sessionId takes precedence; falls back to session_id per spec 3.1."""
        return self.sessionId or self.session_id


class UserEntry(BaseEntry):
    type: Literal["user"] = "user"
    message: MessageModel | None = None
    toolUseResult: str | list[Any] | dict[str, Any] | None = None
    promptId: str | None = None


class AssistantEntry(BaseEntry):
    type: Literal["assistant"] = "assistant"
    message: MessageModel | None = None
    error: bool | None = None
    isApiErrorMessage: bool | None = None


class SystemEntry(BaseEntry):
    type: Literal["system"] = "system"
    content: str | None = None
    subtype: str | None = None
    level: str | None = None
    durationMs: int | None = None
    messageCount: int | None = None
    hasOutput: bool | None = None
    hookErrors: list[str] | None = None
    hookInfos: list[dict[str, Any]] | None = None


class SummaryEntry(BaseEntry):
    type: Literal["summary"] = "summary"
    summary: str
    leafUuid: str | None = None


class AiTitleEntry(BaseEntry):
    type: Literal["ai-title"] = "ai-title"
    aiTitle: str


class AttachmentEntry(BaseEntry):
    """Spec 2.3: attachment entries carry a message but no dedicated rendering."""

    type: Literal["attachment"] = "attachment"
    message: MessageModel | None = None


class QueueOperationEntry(BaseEntry):
    """Spec 2.3: queue-operation entries carry a message."""

    type: Literal["queue-operation"] = "queue-operation"
    message: MessageModel | None = None
    operation: str | None = None


# ---------------------------------------------------------------------------
# History command (history.jsonl)
# ---------------------------------------------------------------------------


class HistoryCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    display: str
    pastedContents: dict[str, Any] = {}
    timestamp: int  # epoch milliseconds
    project: str
    sessionId: str


TranscriptEntry = (
    UserEntry
    | AssistantEntry
    | SystemEntry
    | SummaryEntry
    | AiTitleEntry
    | AttachmentEntry
    | QueueOperationEntry
    | BaseEntry
)
