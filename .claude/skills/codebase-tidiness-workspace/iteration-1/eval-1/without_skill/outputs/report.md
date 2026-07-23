# Codebase Tidiness Report — `src/claude_history_mcp/`

Generated: 2026-07-23  
Scope: `src/claude_history_mcp/` (8 source files, 7 tool files, 2 resource files referenced)  
Scanned for: obsolete code, stale comments, outdated docstrings

---

## Summary

| Severity | Count | Key theme |
|----------|-------|-----------|
| HIGH     | 3     | Inline import, hardcoded limit, fragile dict access |
| MEDIUM   | 8     | Stale regression/fix comments, inconsistent re-export, historical test narratives |
| LOW      | 3     | Cosmetic annotation imprecision, minor structural quirks |

---

## HIGH Severity

### H1 — Inline `import json` inside method body

**File:** `src/claude_history_mcp/search.py:136`  
**Observation:** `import json` is performed inside the `get_session_stats()` method body rather than at the top of the module. This incurs unnecessary import overhead on every invocation and is inconsistent with every other file in the project (which import `json` at module level).

```python
# Current (lazy, inconsistent):
for msg in messages:
    if msg.get("tool_names"):
        try:
            import json
            tools = json.loads(msg["tool_names"])
            ...
```

**Suggested fix:** Move `import json` to the top of `search.py`, alongside the existing `from datetime import ...` and `import dateparser`.

---

### H2 — Hardcoded limit in prefix-based session lookup

**File:** `src/claude_history_mcp/search.py:105`  
**Observation:** `get_session()` retrieves `sessions = self.cache.get_sessions(limit=1000)` when resolving a prefix-based session ID match. If a user accumulates more than 1000 sessions, sessions beyond the 1000th will silently fail prefix matching and return "not found."

```python
sessions = self.cache.get_sessions(limit=1000)
```

**Suggested fix:** Remove the limit entirely or pass a very large sentinel value so all sessions are searched.

---

### H3 — Inconsistent dict key access in `insert_messages()` — potential crash on malformed data

**File:** `src/claude_history_mcp/cache.py:222-249`  
**Observation:** The `insert_messages()` list comprehension uses bracket access (`e["entry_type"]`, `e["uuid"]`, `e["timestamp"]`) for some fields, while using `.get()` with defaults for others. If any entry is missing `uuid`, `raw_json`, or `entry_type`, the entire batch insert will raise `KeyError`.

```python
# Bracket access -- raises KeyError if missing:
e["entry_type"],
e["timestamp"],
e["uuid"],
e["raw_json"],

# .get() with defaults -- safe:
e.get("parent_uuid"),
e.get("is_sidechain", 0),
```

**Suggested fix:** Use `.get()` with sensible defaults for all fields, or validate entries before insertion with a clear error message.

---

## MEDIUM Severity

### M1 — Stale fix comment in `loader.py`

**File:** `src/claude_history_mcp/loader.py:220`  
**Observation:** The comment documents a past bug fix:

```python
# Roll session aggregates up to the project row (fix: previously never
# written, so list_projects() always reported zero messages/tokens).
```

The parenthetical "previously never written" is historical noise. Once a fix is applied, the rationale should live in the git log, not in the source.

**Suggested fix:** Reduce to:
```python
# Roll session aggregates up to the project row.
```

---

### M2 — Regression-test docstrings framed as historical comparisons

**Files:**
- `tests/test_cache.py:97-101`
- `tests/test_cache.py:188-191`
- `tests/test_cache.py:263-267`
- `tests/test_loader.py:124-126`
- `tests/test_search.py:174-177`
- `tests/test_server.py:1-9`
- `tests/test_discovery.py:47`

**Observation:** Multiple test docstrings and comments explain the test in terms of what "the original blueprint" did wrong. For example, the module-level docstring in `test_server.py`:

```python
"""MCP server integration tests using FastMCP v3 Client (in-memory transport).

Regression note: the original blueprint's test suite treated
`client.call_tool(...)` as if it returned a plain list of content blocks
(...). In the installed fastmcp==3.4.4, `call_tool` returns a
`CallToolResult` dataclass with `.data` (...), `.content`, and `.is_error`.
These tests use `.data` directly instead.
"""
```

Once code has shipped, the "original blueprint" framing is unnecessary context for future maintainers. The important information is what the test validates, not who broke it.

**Suggested fix:** Rewrite each docstring/comment to describe what the test verifies without historical framing. For example, for `test_server.py`:
```python
"""MCP server integration tests using FastMCP v3 Client (in-memory transport)."""
```

---

### M3 — Inconsistent re-export of `parse_timestamp`

**File:** `src/claude_history_mcp/parser.py:25-26`  
**Observation:** `parser.py` re-exports `parse_timestamp` from `utils.py` with the comment:

```python
# Re-exported so callers (e.g. loader.py) have one place to import from.
```

However, `loader.py` already imports `scrub_surrogates` and `get_projects_dir` directly from `utils.py`, bypassing the "one place" pattern. The re-export therefore misleads about the convention.

**Suggested fix:** Either:
- Drop the re-export and update `loader.py` to import `parse_timestamp` from `utils.py` directly, or
- Re-export all shared utilities through `parser.py` and import them all from there.

---

## LOW Severity

### L1 — Imprecise return type for `SearchEngine.get_session()`

**File:** `src/claude_history_mcp/search.py:100-121`  
**Annotation:** `def get_session(self, session_id: str) -> dict | None:`  
**Observation:** The method can return `{"error": "ambiguous_prefix", "candidates": [...]}` as a dict on prefix-match ambiguity. While `dict` technically covers this case, the annotation implies the dict is always a successful result. The error-path dict is indistinguishable at the type level.

**Suggested fix:** Either add a `TypedDict` variant or document the error return in the docstring.

---

### L2 — Module-level `_utcnow()` could be a static method

**File:** `src/claude_history_mcp/cache.py:82-83`  
**Observation:** `_utcnow()` is a module-level helper used only by `CacheManager`. Defining it as a `@staticmethod` inside `CacheManager` would be more encapsulated and consistent with the class's design.

**Suggested fix:** Move `_utcnow()` inside `CacheManager` as a static method.

---

### L3 — Redundant section-comment headers in `cache.py`

**File:** `src/claude_history_mcp/cache.py` (lines 117, 165, 221, 291, 313, 348)  
**Observation:** The `# --- Project CRUD ---`, `# --- Session CRUD ---`, etc. section comments are visually redundant with the method names. They add noise in a file that is already well-organized by function groupings.

**Suggested fix:** Remove the decorative comment headers; let the method signatures speak for themselves.

---

## Summary of Suggested Work Items

| Ref | Severity | File | Suggested action |
|-----|----------|------|------------------|
| H1  | HIGH     | `search.py:136` | Move `import json` to top of module |
| H2  | HIGH     | `search.py:105` | Remove hardcoded limit in prefix session lookup |
| H3  | HIGH     | `cache.py:226-249` | Use `.get()` for all dict field access in `insert_messages` |
| M1  | MEDIUM   | `loader.py:220` | Trim stale fix-parenthetical from comment |
| M2  | MEDIUM   | 7 test files | Rewrite "original blueprint" regression comments as plain "what is being tested" docstrings |
| M3  | MEDIUM   | `parser.py:25-26` | Reconcile inconsistent re-export convention |
| L1  | LOW      | `search.py:100` | Document error return in `get_session()` docstring |
| L2  | LOW      | `cache.py:82-83` | Move `_utcnow()` into CacheManager |
| L3  | LOW      | `cache.py:117,165,221,...` | Remove decorative section-comment headers |

---

## Notes

- **No dead code found.** Every function and method is referenced at least once.
- **No entirely unused imports** were found in the source modules.
- **All tool definitions match their MCP manifest** (7 tools, 2 resources, names and signatures consistent).
- **All public-facing docstrings describe current behavior accurately**; the issues are in internal comments and test narrative, not in interface docs.
- The `get_stats()` method on `CacheManager` (`cache.py:355`) is called from test code, so it is active code, not dead.
