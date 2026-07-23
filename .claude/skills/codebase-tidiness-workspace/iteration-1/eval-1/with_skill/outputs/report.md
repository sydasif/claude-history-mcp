# Codebase Tidiness Report -- src/claude_history_mcp/

**Scanned:** 9 files across `/data/projects/claude-history-mcp/src/claude_history_mcp/`

**Scan date:** 2026-07-23

**Tier 1 tools used:** ruff (F401, F841, ERA, FIX, D) | Vulture blocked by permissions -- manual analysis substituted

**Tier 2:** contextual analysis of docstrings, comments, signatures, and dead-code patterns

---

## Summary

| Category | Count |
|---|---|
| High (certain issues, safe to act on) | 4 |
| Medium (likely issues, verify first) | 6 |
| Info (minor / tracking items) | 6 |
| **Total** | **16** |

Of these, 6 findings are in newly modified files (working tree changes) and 10 are pre-existing.

---

## High (certain issues, safe to act on)

| File | Line | Issue | Suggestion |
|---|---|---|---|
| `models.py` | 167-173 | `HistoryCommand` class is defined but never instantiated or imported anywhere in the codebase. The loader constructs plain dicts and passes them to `insert_history_commands` directly. | Remove the `HistoryCommand` model class entirely. |
| `loader.py` | 219-220 | Fix-narrative comment: `# Roll session aggregates up to the project row (fix: previously never written, so list_projects() always reported zero messages/tokens).` | Remove or shorten to present tense, e.g. `# Roll session aggregates up to the parent project row.` |
| `search.py` | 136 | `import json` inside method body (`get_session_stats()`). Every call re-imports the module. | Move `import json` to the top of the file. |
| `search.py` | 141 | `try-except-pass` on `json.loads(msg["tool_names"])` -- silently swallows any parse error. | Log a warning or replace with `json.loads(msg["tool_names"]) if msg.get("tool_names") else []` so the exception is never thrown. |

---

## Medium (likely issues, verify first)

| File | Line | Issue | Suggestion |
|---|---|---|---|
| `server.py` | 16-21 | `_get_engine()` uses `global _engine` (PLW0603) and has no return type annotation (ANN202). | Add `-> SearchEngine` return type annotation. |
| `server.py` | 117, 155 | Magic number `8` used for minimum session ID length check. | Replace with a named constant at module level, e.g. `MIN_SESSION_ID_LENGTH = 8`. |
| `cache.py` | 181, 187 | `upsert_session()` builds SQL with f-strings from `kwargs` keys (S608). If a caller passes an unexpected key, it becomes part of the SQL query. | Validate `kwargs` keys against an allowlist of known column names before building the query. |
| `cache.py` | 352 | `clear_all()` builds SQL with f-string table name (S608). | Use parameterised query or validate table name against an allowlist. |
| `search.py` | 184 | `datetime.fromtimestamp(ts / 1000)` called without `tz` argument (DTZ006). Returns a naive datetime whose meaning depends on the local clock. | Use `datetime.fromtimestamp(ts / 1000, tz=timezone.utc)`. |
| `search.py` | 196 | `datetime.now(timezone.utc)` should use `datetime.UTC` alias (UP017). | Replace `timezone.utc` with `UTC` alias for Python 3.12+ consistency. |

---

## Info (minor / tracking items)

| File | Line | Issue | Suggestion |
|---|---|---|---|
| `__init__.py` | 10 | `__all__` is not sorted (RUF022). | Sort entries alphabetically: `"CacheManager", "SearchEngine", "get_cache_path", "initialize"`. |
| `loader.py` | 205-208 | Early return when no files changed skips `recompute_project_stats()`. If stats were updated externally (e.g. another process), the project row becomes stale. | Call `recompute_project_stats(project_id)` even when no files changed. |
| `discovery.py` | 71 | `open()` should be replaced by `Path.open()` (PTH123). | Use `jsonl_path.open("r", encoding="utf-8", errors="replace")`. |
| `loader.py` | 51, 169 | `open()` should be replaced by `Path.open()` (PTH123). Same pattern as discovery.py. | Use `Path.open(...)`. |
| `utils.py` | 24 | Unnecessary timezone replacement: `ts.replace("Z", "+00:00")` then immediately strips tzinfo with `replace(tzinfo=None)`. | Strip `Z` directly: `ts.replace("Z", "")` and pass to `fromisoformat`, or keep aware datetime for comparison instead of stripping. |
| Various | -- | 42 missing docstrings (ruff D category) across `CacheManager`, `ProjectInfo`, `SessionFileInfo`, `LoadResult`, all model classes, and `SearchEngine.__init__`. | Add one-line docstrings to public classes and methods. These are presentation rules, not semantic issues. |

---

## Notes

### Already fixed in working tree (not in report, verified clean)

The following fix-narrative docstrings and stale comments were already cleaned up in uncommitted changes on `main` (verified via `git diff`):

- `cache.py:131` -- `recompute_project_stats` docstring: removed four-line fix-narrative paragraph
- `cache.py:260` -- `search_messages` docstring: removed eight-line fix-narrative paragraph
- `cache.py:294` -- `insert_history_commands` docstring: removed six-line fix-narrative paragraph
- `parser.py:25` -- re-export comment: trimmed from four-line historical note to one line
- `utils.py:1-3` -- module docstring: removed `NOTE:` paragraph about original blueprint
- `search.py:194` -- `get_recent_activity` docstring: removed fix-narrative paragraph, added `limit` param
- `utils.py:26-28` -- removed `epoch_ms_to_datetime()` (dead code function, deleted)

These align with the "fix-narrative docstring" pattern documented in `references/stale-patterns.md`.

### Ruff ALL lint summary

`ruff check --select ALL src/claude_history_mcp/` reported 165 errors total. The most actionable subset is captured above. The remaining findings are largely:

- **N815** (mixedCase field names) -- intentional, matches JSONL spec camelCase field names
- **BLE001** (blind `except Exception`) -- exists in multiple files; these are defense-in-depth wrappers around JSON parsing and DB operations
- **FBT001/FBT002** (boolean-typed arguments) -- acceptable in configuration-like params
- **PERF401** (list comprehension vs loop) -- minor performance nits
- **E501** (line length) -- 12 violations, mostly in SQL strings

### Dead code

Vulture did not complete due to sandbox restrictions. Manual analysis found `HistoryCommand` as the only fully unused definition. No other dead functions, classes, or variables were identified via manual cross-reference.
