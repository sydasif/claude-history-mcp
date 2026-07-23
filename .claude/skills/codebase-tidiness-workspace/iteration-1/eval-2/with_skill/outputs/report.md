# Docstring Review Report

**Files reviewed:**

- `src/claude_history_mcp/cache.py` (363 lines)
- `src/claude_history_mcp/search.py` (223 lines)

**Date:** 2026-07-23

---

## Summary

| Category                                      | Count |
| --------------------------------------------- | ----- |
| Stale fix-narratives                          | 0     |
| Signature-docstring mismatches                | 2     |
| Descriptions that don't match actual behavior | 4     |
| Missing docstrings (public methods)           | 15    |

---

## 1. Stale Fix-Narratives

**None found.** Neither file contains docstrings that reference old bug-fix behavior that is no longer relevant. The `get_recent_activity` docstring in `search.py:194` references external document "spec 3.2" for the timestamp-less entry survival behavior, but that behavior is still present in the code, so it is not stale.

---

## 2. Signature-Docstring Mismatches

### 2.1 `search.py::SearchEngine.get_recent_activity` (line 194)

The signature has two parameters (`hours: int = 24`, `limit: int = 100`), but the docstring mentions neither. It only describes the return value and a special-case behavior.

### 2.2 `search.py::SearchEngine.search_history` (line 168)

The signature accepts `project`, `from_date`, `to_date`, and `limit`, but the docstring is simply `"Search command history."` with no parameter documentation. A reader cannot tell from the docstring that date filtering or project filtering is supported.

---

## 3. Descriptions That Don't Match Actual Behavior

### 3.1 `search.py::SearchEngine.get_recent_activity` (line 194)

> Docstring: "Get recent messages across all projects."

The SQL at line 201 filters to `entry_type IN ('user', 'assistant')`, so it does NOT return "recent messages" of all types -- it returns only user prompts and assistant responses, excluding tool results, system messages, tool uses, error entries, and other entry types. The docstring overstates the breadth.

### 3.2 `search.py::SearchEngine.get_session_stats` (line 122)

> Docstring: "Get token usage and tool statistics for a session."

The function returns a dict with 7 fields: `session_id`, `project`, `duration_minutes`, `total_input_tokens`, `total_output_tokens`, `message_count`, `tool_usage`, `models_used`, `error_count`. The docstring documents only 2 of these (token usage and tool statistics), omitting duration, message count, models, and errors.

### 3.3 `search.py::SearchEngine.get_session` (line 100)

> Docstring: "Get full session with messages."

The function also falls back to prefix matching when exact lookup fails, and returns an `{"error": "ambiguous_prefix", "candidates": [...]}` dict when multiple sessions share the same prefix. The docstring describes only the happy path and omits the error-return and prefix-matching behaviors.

### 3.4 `search.py::SearchEngine.search_history` (line 176)

> Docstring: "Search command history."

When `from_date`/`to_date` are provided, the function post-filters results by comparing `timestamp_epoch`. The docstring implies a raw search but the function actively applies date-range filtering.

---

## 4. Missing Docstrings (Public Methods)

### `cache.py`

| Line | Method                          |
| ---- | ------------------------------- |
| 87   | `CacheManager.__init__`         |
| 92   | `CacheManager.connect`          |
| 102  | `CacheManager.close`            |
| 107  | `CacheManager.transaction`      |
| 118  | `CacheManager.upsert_project`   |
| 157  | `CacheManager.get_project`      |
| 161  | `CacheManager.get_all_projects` |
| 166  | `CacheManager.upsert_session`   |
| 196  | `CacheManager.get_sessions`     |
| 213  | `CacheManager.get_session`      |
| 303  | `CacheManager.search_history`   |
| 314  | `CacheManager.get_file_mtime`   |
| 320  | `CacheManager.set_file_mtime`   |
| 349  | `CacheManager.clear_all`        |
| 355  | `CacheManager.get_stats`        |

15 public methods in `cache.py` have no docstring at all. The `search.py` file fares better since all its methods have at least a one-liner.

---

## 5. Additional Observations

### 5.1 Parameter naming inconsistency in `cache.py:search_messages` (line 252)

The parameter is named `role` but the SQL maps it to `entry_type`:

```python
if role:
    sql += " AND m.entry_type=?"
```

The name `role` is misleading -- it actually filters by entry type (`user`, `assistant`, `tool_use`, etc.), not by conversational role. This could confuse callers who pass a tool name as the "role."

### 5.2 Google-style docstrings not used

The user's global CLAUDE.md (Python Development Rules) specifies Google-style docstrings with `Args:`, `Returns:`, `Raises:` sections. None of the existing docstrings in either file follow that convention.

### 5.3 `_parse_natural_date` parameter conflict (search.py:209)

The `start_of_day` and `end_of_day` boolean parameters can both be True simultaneously. When that happens, `end_of_day` silently overrides `start_of_day` because it applies second. This is a code design issue exposed by the lack of parameter documentation.

---

## Recommendations

1. **Fix `get_recent_activity` docstring** to document both `hours` and `limit` parameters, and clarify the entry-type filter (`'user', 'assistant'` only).
2. **Expand `get_session_stats` docstring** to list all returned fields (duration, message count, models, errors).
3. **Update `get_session` docstring** to describe prefix-matching fallback and the ambiguous-prefix error dict.
4. **Expand `search_history` docstring** to document the `from_date`/`to_date` filtering behavior.
5. **Add docstrings** to all 15 undocumented public methods in `cache.py`.
6. **Consider adopting Google-style docstrings** across the project per stated Python standards.
