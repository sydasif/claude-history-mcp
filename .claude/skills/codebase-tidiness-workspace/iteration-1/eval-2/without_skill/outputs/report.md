# Docstring Review Report

**Files reviewed:**
- `/data/projects/claude-history-mcp/src/claude_history_mcp/cache.py` (363 lines)
- `/data/projects/claude-history-mcp/src/claude_history_mcp/search.py` (223 lines)

**Date:** 2026-07-23

---

## Summary

| Category | cache.py | search.py |
|---|---|---|
| Stale fix-narratives in docstrings | 0 | 0 |
| Signature-docstring mismatches | 0 | 0 |
| Descriptions that don't match behavior | 0 | 0 |
| Missing docstrings | 11 | 1 |
| Incomplete/minimal docstrings | 3 | 5 |

No stale fix-narratives, signature-docstring mismatches, or factually-wrong descriptions were found. The file-level module docstrings and the docstrings that exist are accurate descriptions of current behavior. The main issues are **missing docstrings** (primarily in `cache.py`) and **incomplete docstrings** (both files).

---

## Category 1: Stale Fix-Narratives

**Result: None found in either file.**

No docstring contains dated fix descriptions, "now" clauses describing a behavioral change, or past-tense bug fix narratives. The CLAUDE.md project instructions reference two fixes (2026-07-23: `get_recent_activity` limit parameter, timezone handling), but neither fix left behind a stale narrative comment in the source code.

**One note:** `_parse_natural_date` (search.py:216) has a code comment `# Ensure naive UTC datetime for comparison with parse_timestamp results` — this is an inline code comment explaining a `replace(tzinfo=None)` call, not a docstring. It documents *current design rationale*, not a past fix, so it is not stale.

---

## Category 2: Signature-Docstring Mismatches

**Result: None found in either file.**

Every existing docstring correctly reflects the presence and purpose of the function it documents. There are no cases of:
- Parameters mentioned in the docstring that do not exist in the signature
- Signature parameters mentioned with incorrect names or types in the docstring
- Return type mismatches

---

## Category 3: Descriptions That Don't Match Behavior

**Result: None found in either file.**

Every existing docstring accurately describes what its function does. However, many docstrings are so minimal that they omit key behavioral details. See "Incomplete/Minimal Docstrings" below for these cases.

---

## Missing Docstrings

### cache.py — 11 public methods lack docstrings entirely

These methods are part of the `CacheManager` class and represent the cache layer's public API. Per Google-style docstring standards expected by the project, each should document parameters and return values.

| Line | Method | Notes |
|---|---|---|
| 118 | `upsert_project` | CRUD method, not self-explanatory (upsert semantics differ by DB) |
| 157 | `get_project` | Simple getter, but accepts `project_path` and returns `dict or None` |
| 161 | `get_all_projects` | Returns all projects ordered by last_updated DESC |
| 166 | `upsert_session` | Dynamic SQL builder with `**kwargs` — behavior is non-trivial |
| 196 | `get_sessions` | JOINs with projects table, orders by last_timestamp DESC |
| 213 | `get_session` | Single-session lookup |
| 303 | `search_history` | LIKE search on `display` column with optional project filter |
| 314 | `get_file_mtime` | Cache invalidation helper |
| 321 | `set_file_mtime` | Cache invalidation helper |
| 349 | `clear_all` | Truncates all 5 tables — dangerous operation with no docstring |
| 355 | `get_stats` | Returns aggregate counts from all tables |

### search.py — 1 method lacks a docstring

| Line | Method | Notes |
|---|---|---|
| 209 | `_parse_natural_date` | Private but non-trivial. Sets TIMEZONE=UTC, strips timezone awareness, clips to start/end of day. The only helper function that bridges `dateparser` output into the system's naive-UTC convention. |

---

## Incomplete/Minimal Docstrings

### cache.py

| Line | Method | Docstring | Gap |
|---|---|---|---|
| 222-223 | `insert_messages` | "Insert parsed entries into messages table." | Does not document the `file_name` parameter, the expected keys in each `entries` dict, or the fact that `entries` is inserted via `executemany`. |
| 260 | `search_messages` | "Substring search across messages." | Does not document that `role` is compared against `entry_type` (not an MCP role), or that the search is case-sensitive `LIKE`. |
| 339-340 | `clear_project_messages` | "Clear messages for a project/session (for reparse)." | `session_id` defaults to `None`; when `None`, all messages for the project are cleared. The docstring does not clarify this behavior. |

### search.py

| Line | Method | Docstring | Gap |
|---|---|---|---|
| 26 | `list_sessions` | "List sessions with optional filters." | Does not document the overfetch-then-filter strategy (limit * 2), the project substring match heuristic (project_path + display_name), or that timestamp-less entries always survive date filters. |
| 64 | `search_messages` | "Search messages with multiple filters." | Does not document that `role` maps to `entry_type`, that `project` uses substring matching, or that `tool_name` is post-filtered (not in SQL). |
| 100-101 | `get_session` | "Get full session with messages." | Omits the most interesting behaviors: prefix-based session-ID matching (minimum 8 chars), the ambiguous-prefix error return `{"error": "ambiguous_prefix", "candidates": [...]}`, and the 1000-session pre-fetch limit. |
| 123 | `get_session_stats` | "Get token usage and tool statistics for a session." | Returns a rich dict with `duration_minutes`, `tool_usage`, `models_used`, `error_count`, `message_count`, `project` — none of these are documented. The `tool_names` JSON deserialization fallback is also undocumented. |
| 176 | `search_history` | "Search command history." | Does not document that `project` is a `LIKE` match, that `timestamp_epoch` is divided by 1000 (milliseconds to seconds), or the overfetch-then-filter pattern for date filtering. |

---

## Recommendations

1. **Add docstrings to all 12 missing cases** in `cache.py` and `search.py`, following Google-style with `Args:` and `Returns:` sections.
2. **Expand the 8 incomplete docstrings** to document non-obvious parameters (`role` mapping to `entry_type`, `session_id=None` semantics, prefix matching behavior, error return shapes).
3. **No action needed** for Category 1/2/3 issues — none were found.
