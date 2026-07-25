# Claude History MCP Server — Developer Specification

## 1. Overview

An MCP server that lets Claude Code query its own session history stored in `~/.claude/projects/**/*.jsonl` and `~/.claude/history.jsonl`. Exposes tools for searching messages, listing sessions, retrieving conversation transcripts, and computing usage statistics.

**Stack**: Python 3.12+, FastMCP v3 (`fastmcp>=3.4`), Pydantic v2, SQLite, `uv` packaging.

**Architecture**: Uses [claude-code-log](https://github.com/daaain/claude-code-log) as a library for all JSONL parsing. That library handles all real-world edge cases (surrogate chars, missing timestamps, dual sessionId/session_id, truncated tool names, tool_result variants, API errors). The MCP server focuses on:

- SQLite cache with incremental mtime-based invalidation
- Full-text search across all messages
- MCP tool/resource exposure via FastMCP

## 2. JSONL Data Model

### 2.1 Two Data Sources

| Source              | Location                                               | Content                           |
| ------------------- | ------------------------------------------------------ | --------------------------------- |
| Command history     | `~/.claude/history.jsonl`                              | Append-only log of user inputs    |
| Session transcripts | `~/.claude/projects/<encoded-path>/<session-id>.jsonl` | Full conversation with tool calls |

### 2.2 Command History Format (`history.jsonl`)

Each line is a JSON object:

```json
{
  "display": "the text typed",
  "pastedContents": {},
  "timestamp": 1784532628943,
  "project": "/home/zulu/litellm-proxy",
  "sessionId": "a7431e9a-48bb-44c9-b2cf-84121bf94917"
}
```

Fields: `display` (str), `pastedContents` (dict), `timestamp` (epoch ms int), `project` (str), `sessionId` (str).

### 2.3 Session Transcript Format

Each line is a JSON object with a `type` discriminator:

#### Entry Types

| `type`                  | Model                           | Has `message`       | Has `uuid`/`parentUuid` |
| ----------------------- | ------------------------------- | ------------------- | ----------------------- |
| `user`                  | `UserTranscriptEntry`           | Yes                 | Yes                     |
| `assistant`             | `AssistantTranscriptEntry`      | Yes                 | Yes                     |
| `system`                | `SystemTranscriptEntry`         | No (uses `content`) | Yes                     |
| `summary`               | `SummaryTranscriptEntry`        | No (uses `summary`) | No                      |
| `ai-title`              | `AiTitleTranscriptEntry`        | No (uses `aiTitle`) | No                      |
| `attachment`            | `AttachmentTranscriptEntry`     | Yes                 | Yes                     |
| `queue-operation`       | `QueueOperationTranscriptEntry` | Yes                 | Yes                     |
| `file-history-snapshot` | Skip                            | No                  | No                      |
| `mode`                  | Skip                            | No                  | No                      |
| `permission-mode`       | Skip                            | No                  | No                      |
| `custom-title`          | Skip                            | No                  | No                      |
| `agent-name`            | Skip                            | No                  | No                      |
| `agent-color`           | Skip                            | No                  | No                      |
| `frame-link`            | Skip                            | No                  | No                      |
| `last-prompt`           | Skip                            | No                  | No                      |

#### Base Entry Fields

```python
{
    "uuid": str,                    # unique message ID
    "parentUuid": str | None,       # parent message ID (DAG chain)
    "sessionId": str,               # session identifier
    "timestamp": str,               # ISO 8601 "YYYY-MM-DDTHH:MM:SS.mmmZ"
    "type": str,                    # entry type discriminator
    "isSidechain": bool,            # True for subagent entries
    "userType": str,                # "external" | "tool_result" | ...
    "cwd": str,                     # working directory
    "version": str,                 # Claude Code version e.g. "2.1.205"
    "gitBranch": str | None,        # git branch when available
    "isMeta": bool | None,          # True for slash commands
    "agentId": str | None,          # agent membership ID
    "spawnedAgentId": str | None,   # agent origin ID (set by loader)
    "teamName": str | None,         # active team name
}
```

#### User Message Structure

```python
{
    "type": "user",
    "message": {
        "role": "user",
        "content": [ContentItem, ...],
        "usage": UsageInfo | None
    },
    "toolUseResult": str | list | dict | None,  # tool callback results
    "promptId": str | None,
    "permissionMode": str | None,
    "origin": {"kind": "human"} | None,
    "mcpMeta": dict | None,
}
```

#### Assistant Message Structure

```python
{
    "type": "assistant",
    "message": {
        "id": str,
        "type": "message",
        "role": "assistant",
        "model": str,               # e.g. "claude-sonnet-5-20250514"
        "content": [ContentItem, ...],
        "stop_reason": str | None,
        "usage": UsageInfo | None,
    },
    "requestId": str | None,
    "error": bool | None,           # True on API errors
    "isApiErrorMessage": bool | None,
}
```

### 2.4 Content Block Types

```python
ContentItem = TextContent | ToolUseContent | ToolResultContent | ThinkingContent | ImageContent

TextContent:
    type: "text"
    text: str

ToolUseContent:
    type: "tool_use"
    id: str                        # tool_use_id for pairing
    name: str                      # tool name e.g. "Bash", "Read", "mcp__obsidian__vault_read"
    input: dict                    # tool-specific input

ToolResultContent:
    type: "tool_result"
    tool_use_id: str               # pairs with ToolUseContent.id
    content: str | list[dict]      # string or array of content blocks
    is_error: bool | None

ThinkingContent:
    type: "thinking"
    thinking: str
    signature: str | None          # Anthropic extended thinking signature

ImageContent:
    type: "image"
    source: {"type": "base64", "media_type": str, "data": str}
```

### 2.5 Usage Info

```python
UsageInfo:
    input_tokens: int | None
    output_tokens: int | None
    cache_creation_input_tokens: int | None
    cache_read_input_tokens: int | None
    server_tool_use: dict | None
    service_tier: str | None
```

### 2.6 System Entry Fields

```python
SystemTranscriptEntry:
    type: "system"
    subtype: str | None            # "stop_hook_summary" | "away_summary" | "compact_boundary" | "local_command"
    content: str | None
    level: str | None              # "warning" | "info" | "error"
    durationMs: int | None
    messageCount: int | None
    hasOutput: bool | None
    hookErrors: list[str] | None
    hookInfos: list[dict] | None
```

---

## 3. Edge Cases to Handle

### 3.1 Dual Session ID Fields

Entries may have both `session_id` (snake_case) and `sessionId` (camelCase). Same value. **Rule**: always use `sessionId`, fall back to `session_id`.

### 3.2 Missing Timestamps

~21% of entries lack timestamps (concentrated on `attachment`, `file-history-snapshot`, `ai-title`, `last-prompt`, `mode`, `permission-mode`). **Rule**: entries without timestamps survive date filtering (always included).

### 3.3 Corrupted Tool Names

Real data contains truncated MCP tool names like `Bcp__plugin_web-search...` (missing `mcp__p` prefix). **Rule**: store tool names as-is, no normalization.

### 3.4 Surrogate Characters

JSONL files may contain lone surrogates (U+D800–U+DFFF) from raw byte decoding. **Rule**: apply `scrub_surrogates()` before SQLite binding:

```python
def scrub_surrogates(s: str | None) -> str | None:
    if s is None:
        return None
    s = re.sub(r"[\ud800-\udbff]", "�", s)
    return s.encode("utf-8", errors="surrogateescape").decode("utf-8", errors="replace")
```

### 3.5 tool_result Content Variants

- Most common: plain `str` (e.g., `"Bash completed with no output"`)
- Sometimes: `list[1]` of `{"type": "text", "text": "..."}` blocks
- **Rule**: if `list`, extract text from first `TextContent` block; if `str`, use directly.

### 3.6 API Error Entries

Some assistant entries have `error: true` + `isApiErrorMessage: true` with text content blocks containing error messages. **Rule**: include in search results, mark as errors.

### 3.7 Entry Types Without `message`

`file-history-snapshot`, `mode`, `permission-mode`, `custom-title`, `agent-name`, `agent-color`, `frame-link`, `last-prompt` lack `message`, `uuid`, `parentUuid`. **Rule**: skip during parsing (SILENT_SKIP_TYPES).

### 3.8 Encoding

JSONL files use `utf-8` encoding with `errors="replace"` fallback. **Rule**: always open with `encoding="utf-8", errors="replace"`.

---

## 4. Architecture

```
┌─────────────────────────────────────────────────┐
│                  MCP Server                      │
│                                                  │
│  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │
│  │  Tools   │  │Resources │  │    Parser     │  │
│  │(search,  │  │(sessions,│  │(JSONL→models) │  │
│  │ list,    │  │ history) │  │               │  │
│  │ get,     │  │          │  │               │  │
│  │ stats)   │  │          │  │               │  │
│  └────┬─────┘  └────┬─────┘  └──────┬────────┘  │
│       │              │               │            │
│  ┌────┴──────────────┴───────────────┴────────┐  │
│  │              Cache Layer (SQLite)           │  │
│  │  projects | sessions | messages | history  │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │          File Discovery                     │  │
│  │  ~/.claude/history.jsonl                    │  │
│  │  ~/.claude/projects/**/*.jsonl              │  │
│  └────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

### 4.1 Module Structure

```
claude-history-mcp/
├── pyproject.toml
├── src/
│   └── claude_history_mcp/
│       ├── __init__.py
│       ├── server.py            # MCP server entry point (FastMCP)
│       ├── models.py            # Pydantic models (simplified from claude-code-log)
│       ├── parser.py            # JSONL parsing + factory dispatch
│       ├── cache.py             # SQLite cache layer
│       ├── discovery.py         # File/project discovery
│       ├── search.py            # Full-text + filtered search
│       └── utils.py             # Surrogate handling, timestamp parsing
└── tests/
    ├── test_parser.py
    ├── test_cache.py
    ├── test_search.py
    └── fixtures/
        ├── sample_session.jsonl
        └── sample_history.jsonl
```

---

## 5. Pydantic Models (Simplified)

Only models needed for search/query — skip rendering, DAG, and tool input/output typing.

```python
from enum import Enum
from typing import Optional, Union
from pydantic import BaseModel

class EntryType(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    SUMMARY = "summary"
    AI_TITLE = "ai-title"
    ATTACHMENT = "attachment"
    QUEUE_OPERATION = "queue-operation"

class TextContent(BaseModel):
    type: str = "text"
    text: str

class ToolUseContent(BaseModel):
    type: str = "tool_use"
    id: str
    name: str
    input: dict

class ToolResultContent(BaseModel):
    type: str = "tool_result"
    tool_use_id: str
    content: Union[str, list[dict]]
    is_error: Optional[bool] = None

class ThinkingContent(BaseModel):
    type: str = "thinking"
    thinking: str

class ImageContent(BaseModel):
    type: str = "image"
    source: dict

ContentItem = Union[TextContent, ToolUseContent, ToolResultContent, ThinkingContent, ImageContent]

class UsageInfo(BaseModel):
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cache_creation_input_tokens: Optional[int] = None
    cache_read_input_tokens: Optional[int] = None

class MessageModel(BaseModel):
    role: str
    content: list[ContentItem]
    model: Optional[str] = None
    usage: Optional[UsageInfo] = None
    id: Optional[str] = None

class BaseEntry(BaseModel):
    uuid: Optional[str] = None
    parentUuid: Optional[str] = None
    sessionId: Optional[str] = None
    timestamp: Optional[str] = None
    type: str
    isSidechain: bool = False
    userType: str = ""
    cwd: Optional[str] = None
    version: Optional[str] = None
    gitBranch: Optional[str] = None
    isMeta: Optional[bool] = None
    agentId: Optional[str] = None

class UserEntry(BaseEntry):
    type: str = "user"
    message: Optional[MessageModel] = None
    toolUseResult: Optional[Union[str, list, dict]] = None

class AssistantEntry(BaseEntry):
    type: str = "assistant"
    message: Optional[MessageModel] = None
    error: Optional[bool] = None

class SystemEntry(BaseEntry):
    type: str = "system"
    content: Optional[str] = None
    subtype: Optional[str] = None
    level: Optional[str] = None

class SummaryEntry(BaseModel):
    type: str = "summary"
    summary: str
    leafUuid: Optional[str] = None

class AiTitleEntry(BaseModel):
    type: str = "ai-title"
    aiTitle: str
    sessionId: Optional[str] = None

TranscriptEntry = Union[UserEntry, AssistantEntry, SystemEntry, SummaryEntry, AiTitleEntry, BaseEntry]
```

---

## 6. Parser

### 6.1 Entry Dispatch

```python
SILENT_SKIP_TYPES = frozenset({
    "file-history-snapshot", "last-prompt", "permission-mode",
    "mode", "custom-title", "agent-name", "agent-color", "frame-link",
})

ENTRY_CREATORS = {
    "user": UserEntry.model_validate,
    "assistant": AssistantEntry.model_validate,
    "system": SystemEntry.model_validate,
    "summary": SummaryEntry.model_validate,
    "ai-title": AiTitleEntry.model_validate,
}

def create_entry(data: dict) -> TranscriptEntry | None:
    entry_type = data.get("type", "")
    if entry_type in SILENT_SKIP_TYPES:
        return None
    creator = ENTRY_CREATORS.get(entry_type)
    if creator:
        try:
            return creator(data)
        except Exception:
            return BaseEntry.model_validate(data)  # fallback
    # Unknown type with uuid → keep for searchability
    if data.get("uuid"):
        return BaseEntry.model_validate(data)
    return None
```

### 6.2 Text Extraction

```python
def extract_text(content: list[ContentItem] | None) -> str:
    if not content:
        return ""
    parts = []
    for item in content:
        if isinstance(item, TextContent):
            parts.append(item.text)
        elif isinstance(item, ThinkingContent):
            parts.append(f"[thinking] {item.thinking[:200]}")
        elif isinstance(item, ToolUseContent):
            parts.append(f"[tool: {item.name}]")
    return "\n".join(parts)

def extract_tool_names(content: list[ContentItem] | None) -> list[str]:
    if not content:
        return []
    return [item.name for item in content if isinstance(item, ToolUseContent)]

def extract_tool_result_text(content: str | list[dict] | None) -> str:
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
```

### 6.3 Timestamp Parsing

```python
from datetime import datetime

def parse_timestamp(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
```

---

## 7. SQLite Cache

### 7.1 Schema

```sql
CREATE TABLE projects (
    id INTEGER PRIMARY KEY,
    project_path TEXT UNIQUE NOT NULL,
    display_name TEXT,
    earliest_timestamp TEXT,
    latest_timestamp TEXT,
    total_messages INTEGER DEFAULT 0,
    total_input_tokens INTEGER DEFAULT 0,
    total_output_tokens INTEGER DEFAULT 0,
    cache_version TEXT,
    last_updated TEXT
);

CREATE TABLE sessions (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),
    session_id TEXT NOT NULL,
    summary TEXT,
    ai_title TEXT,
    first_timestamp TEXT,
    last_timestamp TEXT,
    message_count INTEGER DEFAULT 0,
    first_user_message TEXT,
    cwd TEXT,
    total_input_tokens INTEGER DEFAULT 0,
    total_output_tokens INTEGER DEFAULT 0,
    UNIQUE(project_id, session_id)
);

CREATE TABLE messages (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),
    session_id TEXT NOT NULL,
    file_name TEXT NOT NULL,
    entry_type TEXT NOT NULL,
    timestamp TEXT,
    uuid TEXT,
    parent_uuid TEXT,
    is_sidechain INTEGER DEFAULT 0,
    content_text TEXT,              -- extracted searchable text
    tool_names TEXT,                -- JSON array of tool names used
    model TEXT,                     -- assistant model name
    tokens_input INTEGER,
    tokens_output INTEGER,
    is_error INTEGER DEFAULT 0,
    raw_json TEXT NOT NULL          -- full entry JSON
);

CREATE TABLE history_commands (
    id INTEGER PRIMARY KEY,
    display TEXT NOT NULL,
    project TEXT,
    session_id TEXT,
    timestamp_epoch INTEGER         -- epoch milliseconds
);

CREATE INDEX idx_messages_session ON messages(session_id);
CREATE INDEX idx_messages_type ON messages(entry_type);
CREATE INDEX idx_messages_timestamp ON messages(timestamp);
CREATE INDEX idx_messages_text ON messages(content_text);
CREATE INDEX idx_messages_project ON messages(project_id);
CREATE INDEX idx_sessions_project ON sessions(project_id);
CREATE INDEX idx_history_project ON history_commands(project);
```

### 7.2 Cache Invalidation

- Track source file `mtime` per cached file
- On rebuild: compare current mtime vs cached mtime, reparse only changed files
- Full rebuild triggered by: `--clear-cache` flag, version change, schema migration
- No subagent fingerprint needed (we skip DAG/sidechain loading)

### 7.3 Content Compression

For `raw_json` column: store full JSON string as-is. For 109 sessions / ~11MB of JSONL, uncompressed is acceptable. If needed later, wrap with `zlib.compress()`.

---

## 8. MCP Tools

### 8.1 `list_projects`

List all discovered projects with metadata.

```python
@mcp.tool
def list_projects() -> list[dict]:
    """List all Claude Code projects with session counts and date ranges."""
    # Returns: [{project_path, display_name, session_count, message_count,
    #            earliest, latest, total_tokens}]
```

### 8.2 `list_sessions`

List sessions for a project or all projects.

```python
@mcp.tool
def list_sessions(
    project: str | None = None,     # filter by project path (partial match)
    from_date: str | None = None,   # natural language: "yesterday", "last week"
    to_date: str | None = None,
    limit: int = 50,
    offset: int = 0,                # pagination: skip N results
) -> list[dict]:
    """List Claude Code sessions with summaries, timestamps, and token usage."""
    # Returns: [{session_id, project, summary, ai_title, first_user_message,
    #            message_count, first_timestamp, last_timestamp,
    #            input_tokens, output_tokens, cwd}]
```

### 8.3 `search_messages`

Full-text search across all messages.

```python
@mcp.tool
def search_messages(
    query: str,                     -- search term (case-insensitive substring)
    project: str | None = None,     -- filter by project
    session_id: str | None = None,  -- filter by session
    role: str | None = None,        -- "user" | "assistant" | "system"
    tool_name: str | None = None,   -- filter by tool used
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 50,
    offset: int = 0,                # pagination: skip N results
) -> list[dict]:
    """Search messages across all Claude Code sessions."""
    # Returns: [{session_id, project, timestamp, role, text_preview,
    #            tool_names, model, tokens}]
```

### 8.4 `get_session`

Get full conversation for a session.

```python
@mcp.tool
def get_session(
    session_id: str,                -- full ID or prefix (min 8 chars)
    include_thinking: bool = False,
    include_tools: bool = True,
) -> dict:
    """Get full conversation transcript for a session."""
    # Returns: {session_id, project, summary, messages: [{timestamp, role,
    #           text, tool_name, tool_input, is_error}]}
```

### 8.5 `get_session_stats`

Token usage and tool statistics for a session.

```python
@mcp.tool
def get_session_stats(session_id: str) -> dict:
    """Get token usage, tool call counts, and duration for a session.
    Supports prefix matching (min 8 chars), same as get_session."""
    # Returns: {session_id, duration_minutes, total_input_tokens,
    #           total_output_tokens, message_count, tool_usage: {Bash: 10, Read: 5, ...},
    #           models_used: ["claude-sonnet-5-20250514"],
    #           error_count}
```

### 8.6 `search_history`

Search the global command history.

```python
@mcp.tool
def search_history(
    query: str,
    project: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 50,
    offset: int = 0,                # pagination: skip N results
) -> list[dict]:
    """Search Claude Code command history."""
    # Returns: [{display, project, session_id, timestamp}]
```

### 8.7 `get_recent_activity`

Get recent activity across all projects.

```python
@mcp.tool
def get_recent_activity(
    hours: int = 24,
    limit: int = 100,
    offset: int = 0,                # pagination: skip N results
) -> list[dict]:
    """Get recent Claude Code activity across all projects."""
    # Returns: [{session_id, project, timestamp, role, text_preview}]
```

---

## 9. MCP Resources

### 9.1 `claude://history`

The global command history as a readable resource.

### 9.2 `claude://projects`

List of all projects as a resource.

---

## 10. File Discovery

### 10.1 Project Directory Encoding

Claude Code encodes absolute paths to directory names:

- `/home/zulu/litellm-proxy` → `-home-zulu-litellm-proxy`
- `/data/blogs` → `-data-blogs`
- Rule: strip leading `/`, replace `/` with `-`

### 10.2 Discovery Algorithm

```python
def discover_projects(projects_dir: Path) -> list[ProjectInfo]:
    """Scan ~/.claude/projects/ for directories containing .jsonl files."""
    for entry in projects_dir.iterdir():
        if entry.is_dir() and not entry.name.startswith("."):
            jsonl_files = list(entry.glob("*.jsonl"))
            if jsonl_files:
                # Extract display name from first JSONL's cwd field
                display_name = extract_cwd_from_file(jsonl_files[0]) or entry.name
                yield ProjectInfo(
                    dir_name=entry.name,
                    display_name=display_name,
                    path=entry,
                    jsonl_files=jsonl_files,
                )
```

### 10.3 History File Discovery

```python
def find_history_file() -> Path | None:
    """Find ~/.claude/history.jsonl."""
    history = Path.home() / ".claude" / "history.jsonl"
    return history if history.exists() else None
```

---

## 11. Search Implementation

### 11.1 Full-Text Search

SQLite `LIKE '%query%'` on `content_text` column. Simple, sufficient for ~11MB dataset. If performance becomes an issue, add FTS5 virtual table later.

### 11.2 Date Filtering

```python
import dateparser

def parse_natural_date(date_str: str) -> datetime | None:
    settings = {"TIMEZONE": "UTC", "RETURN_AS_TIMEZONE_AWARE": False}
    return dateparser.parse(date_str, settings=settings)
```

### 11.3 Session ID Prefix Matching

```python
def find_session(prefix: str) -> list[SessionInfo]:
    """Find sessions where session_id starts with prefix."""
    # SQL: WHERE session_id LIKE '{prefix}%'
    # Return exact matches first, then prefix matches
```

---

## 12. Error Handling

| Scenario                                        | Strategy                                               |
| ----------------------------------------------- | ------------------------------------------------------ |
| Missing `~/.claude/projects/`                   | Return empty results, log warning                      |
| Corrupt JSONL line                              | Skip line, log warning, continue parsing               |
| Missing `message` field on user/assistant entry | Create entry with empty message                        |
| SQLite locked                                   | Retry once with 1s delay, then raise                   |
| Surrogate characters                            | Apply `scrub_surrogates()` before any string operation |
| Unknown entry type with uuid                    | Create `BaseEntry`, include in search                  |
| Unknown entry type without uuid                 | Skip silently                                          |
| Missing timestamps                              | Include in results, sort by file position              |
| `session_id` vs `sessionId`                     | Always prefer `sessionId`, fall back to `session_id`   |
| tool_result as list vs string                   | Normalize: extract text from list, use string directly |
| Empty content list                              | Return empty string from `extract_text()`              |
| API error entries                               | Include in results, flag `is_error=True`               |

---

## 13. Testing Plan

### 13.1 Unit Tests

| Test                         | What it covers                                          |
| ---------------------------- | ------------------------------------------------------- |
| `test_parse_user_entry`      | User message parsing, content extraction                |
| `test_parse_assistant_entry` | Assistant message with tool_use, thinking               |
| `test_parse_system_entry`    | System subtypes (hook_summary, compact_boundary)        |
| `test_parse_summary_entry`   | Summary extraction                                      |
| `test_silent_skip`           | All SILENT_SKIP_TYPES return None                       |
| `test_extract_text`          | TextContent, ThinkingContent, ToolUseContent extraction |
| `test_extract_tool_names`    | Tool name extraction from content blocks                |
| `test_tool_result_string`    | String tool_result normalization                        |
| `test_tool_result_list`      | List tool_result text extraction                        |
| `test_surrogate_handling`    | High/low surrogate scrubbing                            |
| `test_timestamp_parsing`     | ISO 8601 with/without Z, missing timestamps             |
| `test_dual_session_id`       | `session_id` vs `sessionId` fallback                    |
| `test_create_entry_fallback` | Unknown type with uuid → BaseEntry                      |

### 13.2 Integration Tests

| Test                        | What it covers                                      |
| --------------------------- | --------------------------------------------------- |
| `test_parse_real_jsonl`     | Parse actual JSONL files from `~/.claude/projects/` |
| `test_cache_build_and_read` | Build cache from JSONL, read back                   |
| `test_cache_invalidation`   | Modify JSONL, verify reparse                        |
| `test_search_messages`      | Full-text search with various filters               |
| `test_list_sessions`        | Session listing with date filters                   |
| `test_list_projects`        | Project discovery                                   |
| `test_get_session`          | Full session retrieval                              |
| `test_history_parsing`      | Parse `history.jsonl`                               |
| `test_mcp_tool_calls`       | End-to-end MCP tool invocation                      |

### 13.3 Test Fixtures

Create minimal JSONL fixtures covering:

- Normal user/assistant exchange
- Tool use + tool result pairs
- Thinking blocks
- System messages (hook_summary, compact_boundary)
- Entries with missing timestamps
- Entries with missing `message` field
- API error entries
- Entries with surrogate characters
- Dual `session_id`/`sessionId` fields

---

## 14. Implementation Order

| Phase | Task                             | Dependencies      |
| ----- | -------------------------------- | ----------------- |
| 1     | Models (`models.py`)             | None              |
| 2     | Parser (`parser.py`)             | Models            |
| 3     | Cache schema + CRUD (`cache.py`) | Parser            |
| 4     | File discovery (`discovery.py`)  | None              |
| 5     | Search engine (`search.py`)      | Cache             |
| 6     | MCP server + tools (`server.py`) | All above         |
| 7     | Unit tests                       | Models, Parser    |
| 8     | Integration tests                | All above         |
| 9     | Real data validation             | Integration tests |

---

## 15. Configuration

```toml
# pyproject.toml
[project]
name = "claude-history-mcp"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastmcp>=3.4",
    "pydantic>=2.0",
    "dateparser>=1.0",
]

[project.scripts]
claude-history-mcp = "claude_history_mcp.server:main"
```

### Claude Code Integration

```bash
# Add to Claude Code
claude mcp add claude-history -- python -m claude_history_mcp.server

# Or with uvx
claude mcp add claude-history -- uvx claude-history-mcp
```

---

## 16. External Dependency

**claude-code-log** (via `claude_code_log.api`) provides all parsing, validation, and cache management:

- `TranscriptEntry` types (User, Assistant, System, Summary, AiTitle, Attachment, QueueOperation, Base, Passthrough)
- `ContentItem` discriminated union (Text, ToolUse, ToolResult, Thinking, Image)
- `create_transcript_entry()` — validates raw JSON into typed entry
- `extract_text_content()` — extracts searchable text from content blocks
- `parse_timestamp()` — ISO 8601 parsing
- `CacheManager`, `SessionCacheData` — their SQLite cache layer
- `load_transcript()`, `load_directory_transcripts()` — core loading
- `ensure_fresh_cache()` — cache refresh
- `discover_projects()`, `find_history_file()`, `load_history_file()` — discovery

Installed via: `claude-code-log @ git+https://github.com/sydasif/claude-code-log@add-library-api` (until upstream merges the library API PR)

---

## 17. What We Skip (vs claude-code-log)

### 7.4 Cache Pagination

All cache query methods support pagination:

```python
# Messages can be fetched with limit/offset
cache.get_session_messages(session_id, limit=50, offset=0)
```

The `SearchEngine` layers offset-based pagination on top for all list/search tools with overfetch-then-filter approach — it fetches more rows than needed from SQLite, applies in-memory post-filters (tool name, date range), then slices `[offset:offset+limit]` before returning.
