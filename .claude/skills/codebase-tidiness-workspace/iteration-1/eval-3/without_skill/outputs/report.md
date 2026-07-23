# Codebase Tidiness Report

**Date:** 2026-07-23
**Scope:** `src/claude_history_mcp/`
**Tools:** vulture (60% confidence), pyflakes, manual inspection

---

## 1. TODO / FIXME / HACK Markers

**None found.** No TODOs, FIXMEs, HACKs, or XXX markers exist in the source code.

---

## 2. Commented-Out Code Blocks

**None found.** All comments in the codebase are explanatory/narrative (section headers, inline notes, docstrings). No commented-out code was detected.

---

## 3. Unused Functions / Methods / Fields

### 3.1 Genuinely dead (never read anywhere, including tests)

| Location | Symbol | Type | Notes |
|----------|--------|------|-------|
| `discovery.py:12` | `ProjectInfo.dir_name` | Dataclass field | Set on construction but `dir_name` is never accessed by any code in `src/` or `tests/`. The field is dead. |
| `loader.py:18` | `LoadResult.total_entries` | Dataclass field | Assigned at `loader.py:149` as `message_count + skipped + errors` but the value is never read by any code. |
| `loader.py:20` | `LoadResult.skipped_entries` | Dataclass field | Assigned at `loader.py:151` but never read. |

### 3.2 False positives (vulture can't detect decorator/indirect usage)

Vulture flagged these at 60% confidence, but they are actually used:

| Location | Symbol | Reason it's not dead |
|----------|--------|---------------------|
| `server.py:217` | `get_projects_resource` | Registered via `@mcp.resource("claude://projects")` -- invoked by FastMCP framework, never called directly |
| `server.py:233` | `get_history_resource` | Registered via `@mcp.resource("claude://history")` -- same pattern |
| `cache.py:96` | `self._conn.row_factory` | Attribute assignment that configures the sqlite3 connection |
| `cache.py:107` | `CacheManager.transaction` | Context manager used in `tests/test_cache.py:243,253` |
| `cache.py:157` | `CacheManager.get_project` | Used in `tests/test_cache.py` and `tests/test_loader.py` |
| `cache.py:355` | `CacheManager.get_stats` | Used in `tests/test_cache.py` and `tests/test_loader.py` |
| `discovery.py:52` | `discover_all_sessions` | Used in `tests/test_discovery.py` |
| `loader.py:21,24,25` | `error_entries`, `total_input_tokens`, `total_output_tokens` | Read in `tests/test_loader.py` |
| `models.py:104` | `BaseEntry.resolved_session_id` | Defined as public property; available for external callers |

### 3.3 Pydantic model fields (shadow use by Pydantic)

Vulture flagged many fields in Pydantic models (`models.py`). These are **not dead code** -- they define the deserialization schema used by `model_validate()` when parsing JSONL transcripts. Removing them would break parsing of any entry containing those fields.

Examples of such fields: `cache_creation_input_tokens`, `cache_read_input_tokens`, `server_tool_use`, `service_tier`, `userType`, `version`, `gitBranch`, `isMeta`, `agentId`, `spawnedAgentId`, `teamName`, `toolUseResult`, `promptId`, `isApiErrorMessage`, `subtype`, `level`, `durationMs`, `messageCount`, `hasOutput`, `hookErrors`, `hookInfos`, `leafUuid`, `operation`, `pastedContents`, and Pydantic-internal field `id`.

---

## 4. Unused Imports

| File | Line | Import | Status |
|------|------|--------|--------|
| `parser.py:26` | `from .utils import parse_timestamp` | Intentionally re-exported with `# noqa: F401` for caller convenience (`loader.py` imports it from `parser`). Not dead. |
| `tests/test_cache.py:1` | `import json` | **Genuinely unused** -- `json` is never referenced anywhere in the test file. Dead import. |

---

## 5. Additional Observations

### 5.1 Inline import in hot path
`search.py:136-137` contains `import json` inside the `get_session_stats` method body (not at module level). This is a minor style issue -- `json` is a stdlib module so the import cost is negligible, but it's inconsistent with the rest of the codebase where all imports are at module level.

### 5.2 LoadResult fields never consumed
The `LoadResult` dataclass (`loader.py:15-25`) has 3 fields that are populated but never read by any code:
- `total_entries` -- computed costfully but never used
- `skipped_entries` -- computed but never used
- The 3 unused fields inflate the dataclass by 60% (3 of 5 fields are dead)

Only `message_count`, `first_user_message`, `error_entries`, `total_input_tokens`, and `total_output_tokens` are consumed (in tests).

---

## Summary

| Category | Count |
|----------|-------|
| TODO/FIXME/HACK markers | 0 |
| Commented-out code blocks | 0 |
| Genuinely dead code | **3** (2 `LoadResult` fields, 1 `ProjectInfo` field) |
| Unused imports | **1** (`json` in `tests/test_cache.py`, minor `# noqa` in `parser.py` is intentional) |
| Style concerns | 1 (inline import in `search.py:136`) |

**Actionable items (high confidence):**
1. Remove `dir_name` from `ProjectInfo` dataclass (or make it `_dir_name` if needed internally)
2. Remove `total_entries` and `skipped_entries` from `LoadResult` dataclass
3. Remove unused `import json` from `tests/test_cache.py`
4. Move `import json` to module level in `search.py` for consistency
