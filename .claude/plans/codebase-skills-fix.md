# Plan: Fix Codebase Issues & Improve Skill

Two parallel workstreams — codebase fixes (deterministic, sequential) and skill
improvements (iterative). Run codebase fixes first since they also validate
the skill's findings.

---

## Workstream A — Codebase Fixes

All file edits, single-threaded, order matters.

### A1. Remove dead `ProjectInfo.dir_name` field

- **File:** `src/claude_history_mcp/discovery.py:11-12`
- **Change:** Remove `dir_name: str` field from `ProjectInfo` dataclass
- **Remove** `dir_name=entry.name` from `discover_projects()` (line 43)
- **Why:** Field is set but never read anywhere in the codebase

### A2. Remove dead `LoadResult.total_entries` and `skipped_entries`

- **File:** `src/claude_history_mcp/loader.py:18,20`
- **Change:** Remove `total_entries: int` and `skipped_entries: int` from `LoadResult`
- **Remove** corresponding assignments at lines 149 and 151
- **Keep** `error_entries` (read in `tests/test_loader.py:78`)
- **Update** `load_jsonl_file` return at line 149 — remove the two fields
- **Why:** Set but never read; `error_entries` is used so keep it

### A3. Remove unused `import json` in test file

- **File:** `tests/test_cache.py:1`
- **Change:** Delete `import json` — no `json.` usage exists in the file

### A4. Move inline `import json` to module top in search.py

- **File:** `src/claude_history_mcp/search.py:136`
- **Change:** Remove `import json` from inside `get_session_stats()` body
- **Add** `import json` to the top of the file (after `import dateparser`)
- **Why:** Re-imported on every call to `get_session_stats`

### A5. Add column allowlist to `upsert_session`

- **File:** `src/claude_history_mcp/cache.py:166-188`
- **Change:** Add `_ALLOWED_SESSION_COLUMNS = frozenset({...})` at module level.
  Validate each key in `kwargs` against the allowlist before building SQL.
- **Allowed columns:** summary, ai_title, first_timestamp, last_timestamp,
  message_count, cwd, total_input_tokens, total_output_tokens, first_user_message
- **Skip unknown keys silently** (don't crash — just don't inject them into SQL)
- **Why:** `**kwargs` keys are interpolated directly into SQL strings — if a
  caller passes an unexpected key, it becomes part of the query

### A6. Fix timezone-naive `fromtimestamp` in search.py

- **File:** `src/claude_history_mcp/search.py:184`
- **Change:** `datetime.fromtimestamp(ts / 1000, tz=timezone.utc)`
- **Why:** Current call returns a naive datetime whose meaning depends on local clock

### A7. Clean up `parser.py` re-export

- **File:** `src/claude_history_mcp/parser.py:25-26`
- **Change:** Remove the re-export of `parse_timestamp` — loader.py imports
  `parse_timestamp` from parser.py (via `from .parser import ...`)
  but also imports from utils.py directly, making the "single place" pattern
  misleading. Update `loader.py` to import `parse_timestamp` from `utils.py`
  instead of `parser.py`, then remove the re-export line.
- **Why:** The re-export pretends to be a consolidation point, but callers
  import from `utils.py` directly for other symbols anyway

### A8. Verify all changes with tests

- `uv run pytest -v` — all 112+ tests must pass

---

## Workstream B — Skill Improvements (SKILL.md + script)

### B1. Add sweep-depth control

- **File:** `SKILL.md` — new "Depth control" section
- Add a `depth` parameter early in the skill: `quick` (targeted: dead code +
  stale docs + TODOs only) vs `deep` (everything: all ruff rules, docsig,
  docvet, coverage)
- The default is `quick`. `deep` only when the user explicitly asks for a
  comprehensive audit.
- **Why:** Eval 3 with-skill ran `ruff --select ALL` and produced 165 findings,
  overwhelming the specific dead-code ask

### B2. Stronger push for the bundled script

- **File:** `SKILL.md` — replace "Use the bundled script" with a hard
  requirement: "FIRST, run `scripts/scan_codebase.py`. Only fall back to
  ad-hoc tooling if the script fails."
- Add a checklist at the top of Tier 1:
  ```
  1. Run scripts/scan_codebase.py <target> --all (or --skip-* flags)
  2. Read the JSON output
  3. Deduplicate findings
  4. Proceed to Tier 2
  ```
- **Why:** The agent ignored the script in eval 3 and ran ad-hoc ruff instead

### B3. Add working-tree awareness

- **File:** `SKILL.md` — add to Tier 2A (stale fix-narratives)
- Before scanning docstrings, run `git diff HEAD` and `git diff --cached`
  to identify files with uncommitted changes
- For files with uncommitted changes: check both the committed version
  (`git show HEAD:<file>`) and the working tree version for stale docs
- For unchanged files: check only the working tree version
- **Why:** Both evals missed `epoch_ms_to_datetime` because it was already
  removed in the working tree — the skill should know to look at both states

### B4. Add Pydantic model dead-code check

- **File:** `SKILL.md` — add to Tier 2E or new sub-section
- Check: for each Pydantic model class defined in the codebase, is it
  imported (directly or via `__all__`) outside its defining module?
- Models used only in tests are NOT dead — flag as "test-only, consider
  moving" rather than "dead"
- **Why:** `HistoryCommand` in `models.py:167` is defined but only used in
  tests — the skill should flag this

### B5. Update `scripts/scan_codebase.py` — add depth flag

- **File:** `scripts/scan_codebase.py`
- Add `--depth quick|deep` flag
  - `quick` (default): Vulture, Ruff F401/F841/ERA/FIX, docsig
  - `deep`: everything (adds Ruff D, docvet, coverage)
- **Why:** Matches the depth control in SKILL.md so the script respects it too
