# Codebase Tidiness Report

**Source**: `src/claude_history_mcp/` (10 files)
**Date**: 2026-07-23
**Tools**: ruff 0.15.22, vulture 2.16

---

## 1. TODO / FIXME / HACK Markers

**Result: None found.**

The codebase contains zero TODO, FIXME, HACK, or XXX markers. All comments are explanatory or section-separator formatting. No stale action items exist.

---

## 2. Commented-Out Code Blocks

**Result: None found.**

Heuristic scan (lines starting with `#` containing code-like patterns such as `def`, `class`, `return`, `=`, etc.) yielded zero results. All comments in the codebase are natural-language explanations or section dividers.

---

## 3. Vulture Dead Code Analysis

Vulture 2.16 was run on `src/claude_history_mcp/` at 60% confidence threshold. Every reported item was cross-referenced against production call sites and test files.

### True positives (genuinely dead code, even after test check)

None. All vulture-reported items turned out to be false positives when accounting for test coverage and decorator-based registrations.

### False positives (used but not detected by vulture)

| Item | File | Reason |
|------|------|--------|
| `discover_all_sessions()` | `discovery.py:52` | Used in `tests/test_discovery.py:35` |
| `get_project()` | `cache.py:157` | Used in `tests/test_cache.py:27,30,247,260,289` and `tests/test_loader.py:142` |
| `get_stats()` | `cache.py:355` | Used in `tests/test_cache.py:185,196,229,236` and `tests/test_loader.py:132,157` |
| `transaction()` | `cache.py:108` | Used in `tests/test_cache.py:243,253` |
| `get_projects_resource()` | `server.py:217` | Registered via `@mcp.resource("claude://projects")` decorator -- invoked by FastMCP |
| `get_history_resource()` | `server.py:233` | Registered via `@mcp.resource("claude://history")` decorator -- invoked by FastMCP |
| `row_factory` attr | `cache.py:96` | Assigned to `self._conn.row_factory = sqlite3.Row` -- used implicitly by all subsequent queries |
| All Pydantic model fields | `models.py` (22 fields) | Schema definitions for JSONL validation, referenced via `model_validate()` and `isinstance` checks |
| `resolved_session_id` property | `models.py:104` | Defined on `BaseEntry`, callers may access it dynamically |
| `LoadResult` fields | `loader.py:18-25` | Dataclass fields; consumers read the subset they need |
| `HistoryCommand` class | `models.py:167` | Used in `tests/test_models.py:112` |

---

## 4. Ruff Static Analysis

Ruff 0.15.22 was run with default ruleset (`ruff check`) and all rules (`--select=ALL`).

### 4.1 Default Ruleset (37 errors, 8 auto-fixable)

#### Security (S608) -- 3 occurrences

**SQL injection vector through string-based query construction** in `cache.py`:

| Line | Method | Issue |
|------|--------|-------|
| 181 | `upsert_session()` | Dynamic column names from `kwargs` are interpolated via f-string into `INSERT ... DO UPDATE SET {update_str}`. While `kwargs` keys are not user-controlled, this bypasses parameterization. |
| 187 | `upsert_session()` | Same pattern for the `ON CONFLICT` fallback branch. |
| 352 | `clear_all()` | `f"DELETE FROM {table}"` where `table` is from a hard-coded list -- low risk, but flagged. |

**Recommendation**: The `upsert_session` column interpolation (lines 181, 187) is the most concerning. Refactor to build the query from a whitelist of known column names. The `clear_all` loop (line 352) iterates a hard-coded list so risk is minimal.

#### Modernization (UP017) -- 2 occurrences

| File | Line | Current | Should be |
|------|------|---------|-----------|
| `cache.py` | 83 | `datetime.now(timezone.utc)` | `datetime.now(datetime.UTC)` |
| `search.py` | 196 | `datetime.now(timezone.utc)` | `datetime.now(datetime.UTC)` |

`datetime.UTC` was added in Python 3.11 and is the preferred alias.

#### Bare except:pass (S110) -- 2 occurrences

| File | Line | Context |
|------|------|---------|
| `search.py` | 141 | `except Exception: pass` in `get_session_stats()` -- swallowing `json.loads` errors for tool name parsing |
| `server.py` | 140 | `except Exception: pass` in `get_session()` -- swallowing errors when filtering thinking blocks |

**Recommendation**: Replace `pass` with `logger.warning(...)` or a comment explaining why the error is benign.

#### Import ordering (I001) -- 2 occurrences, auto-fixable

| File | Line |
|------|------|
| `loader.py` | 3 |
| `parser.py` | 3 |

Run `uv run ruff check --fix` to auto-sort.

#### Stylistic

| File | Lines | Rule | Description |
|------|-------|------|-------------|
| `models.py` | 43 | UP007 | Use `X | Y` instead of `Union[X, Y]` for type annotations |
| `models.py` | 89-144 | N815 | 18 `mixedCase` variable names in Pydantic model fields (by design -- matches JSONL schema) |
| `discovery.py` | 71 | PTH123 + UP015 | `open()` should be `Path.open()` |
| `loader.py` | 51, 169 | PTH123 + UP015 | Same `open()` -> `Path.open()` |

### 4.2 Full Ruleset (165 errors, 23 auto-fixable)

Beyond the items above, the full ruleset flags:

- **Missing docstrings** (D1xx family) -- ~30 instances across public classes and methods
- **Line length** (E501) -- ~12 lines exceed 100 chars
- **Boolean positional arguments** (FBT001/002) -- `server.py` `get_session(include_thinking=False)`, `loader.py` `load_project(force=False)`
- **Too many branches/statements** (PLR0912/PLR0915) -- `loader.py:load_jsonl_file`: 19 branches, 65 statements
- **Too many arguments** (PLR0913) -- `search.py:search_messages` (8 params), `server.py:search_messages` (8 params)
- **Blind exception catch** (BLE001) -- 8 instances of bare `except Exception`
- **Missing return type annotations** (ANN) -- 6 public functions lack return type hints
- **Magic value comparisons** (PLR2004) -- `server.py` lines 117, 155 use magic number `8` for session_id length check

---

## 5. Summary

| Category | Count | Action Required |
|----------|-------|----------------|
| TODO/FIXME/HACK | 0 | Clean |
| Commented-out code | 0 | Clean |
| Dead code (true positive) | 0 | Clean |
| Security (S608) | 3 | Medium priority -- refactor `upsert_session` dynamic SQL |
| Bare except:pass (S110) | 2 | Low priority -- add logging |
| Python version idioms (UP017) | 2 | Low priority -- replace with `datetime.UTC` |
| Import sorting (I001) | 2 | Trivial -- `ruff check --fix` |
| Open -> Path.open (PTH123) | 3 | Low priority -- mechanical change |
| Docstrings | ~30 | Low priority -- depends on standards |
| Other style issues | ~120 | Discretionary |

### Key takeaway

The codebase is well-maintained with no dead code, no stale TODOs, and no commented-out blocks. The most impactful items to address are the three SQL injection warnings (S608) in `cache.py` -- specifically the dynamic column name interpolation in `upsert_session()`.
