---
name: codebase-tidiness
description: >
  Scan Python codebases for obsolete code, stale comments, and outdated
  docstrings — the kind of cruft that accumulates during development but
  doesn't trigger linter errors. Run this before sprint reviews, after
  large refactors, or whenever the codebase needs a cleanup pass. If the
  user asks to "clean up", "tidy up", "find dead code", "check for stale
  comments", "review docstrings freshness", or mentions "code quality
  pass" or "spring cleaning", invoke this skill — don't assume they just
  mean formatting.
---

A codebase accumulates three kinds of invisible debt faster than most teams
realize: code that nothing calls anymore, comments that describe code that
no longer exists, and docstrings that were accurate once but drifted out of
sync. Linters catch style violations; they don't catch these.

This skill runs a **tiered scan**: mechanical checks first (tools that are
fast and precise), then a contextual pass (model judgment for issues no
tool can flag). The output is a single report with severity, file:line
references, and — where safe — suggested fixes.

---

## Depth control

Choose the scan scope upfront:

- **`quick` (default)** — Focused on the most actionable categories: dead code,
  stale fix-narratives, lying comments, zombie code, contextless TODOs.
  Tier 1 runs Vulture + Ruff F401/F841/ERA/FIX + docsig.
- **`deep`** — Full audit. Adds Ruff D (missing docstrings), docvet freshness
  (stale docs), and Coverage.py (untested code). Use when the user asks for a
  comprehensive sweep or before a major release.

Ask the user which depth they want if they don't specify. Default to `quick`
— deep produces too many findings to act on in one pass.

---

## How it works

### Tier 1 — Automated tooling (fast, deterministic)

**FIRST:** Run `scripts/scan_codebase.py` against the target directory. Do NOT
reach for ad-hoc ruff/vulture commands — the script handles all Tier 1 tools
in one call and outputs structured JSON. Only fall back to manual tool runs
if the script fails.

```
1. cd <project-root>
2. uv run python .claude/skills/codebase-tidiness/scripts/scan_codebase.py <target> [--depth quick|deep]
3. Read the JSON output — findings are grouped by tool
4. Deduplicate overlapping findings (Vulture + Ruff F401 may flag the same import)
5. Proceed to Tier 2
```

Collect all findings from Tier 1 before proceeding to Tier 2 — the context
matters for dedup.

| What                                          | Tool / Approach                                                  | Depth | Why                                                              |
| --------------------------------------------- | ---------------------------------------------------------------- | ----- | ---------------------------------------------------------------- |
| Unused functions, classes, variables, imports | **Vulture** (`vulture <dir> --min-confidence 80`)                | quick | AST-based, fast, per-item confidence scores                      |
| Unused imports & dead variables               | **Ruff** (`ruff check --select F401,F841 <dir>`)                 | quick | Complements Vulture on the import/variable level                 |
| Commented-out code                            | **Ruff** (`ruff check --select ERA <dir>`)                       | quick | Catches `# def old_func():`, `# import x`, etc.                  |
| TODO/FIXME/HACK markers                       | **Ruff** (`ruff check --select FIX <dir>`)                       | quick | Collects all fixme markers for Tier 2 evaluation                 |
| Signature/docstring parameter mismatch        | **docsig** (`docsig --check-class --check-protected <dir>`)      | quick | Ensures `Args:` sections match actual function signatures        |
| Missing docstrings by style                   | **Ruff** (`ruff check --select D <dir>`)                         | deep  | Catches missing docs; does _not_ catch semantic staleness        |
| Stale docstrings (fast, changed files only)   | **docvet diff mode** (`docvet check --freshness <dir>`)          | deep  | Detects code changes without docstring updates; runs on git diff |
| Stale docstrings (full blame sweep)           | **docvet drift mode** (`docvet check --freshness --drift <dir>`) | deep  | Uses git blame to find docstrings that fell behind gradually     |
| Code unreachable by test coverage             | **Coverage.py** (if test suite is available)                     | deep  | Low-confidence but useful signal                                 |

**Key insight about docstring staleness tools:**

| Tool             | What it catches                                         | What it misses                                               |
| ---------------- | ------------------------------------------------------- | ------------------------------------------------------------ |
| **docsig**       | Parameter name/type drift, extra/missing params         | Changed logic/behavior without signature change              |
| **docvet diff**  | Docstrings not updated alongside code in recent commits | Docstrings that were already stale before the diff           |
| **docvet drift** | Gradual docstring rot across the full git history       | No false positives from squash merges or reformats           |
| **Ruff D**       | Missing docstrings entirely                             | Content correctness — it only checks _presence_ and _format_ |

These tools are **complementary**. docvet catches behavioral staleness (code
changed but docs didn't), and docsig catches structural staleness (signature
drifted from docs). Use both.

**Script flags:**

- `--depth quick` (default): Vulture, Ruff F401/F841/ERA/FIX, docsig
- `--depth deep`: everything above + Ruff D, docvet, coverage.py
- `--skip-*` flags override individual tools within any depth
- `--all` runs everything regardless of depth (same as `--depth deep`)

**Vulture tips:**

- `--min-confidence 80` avoids most false positives from dynamic dispatch
- Vulture tracks names, not call graphs — findings at 60-80% confidence are
  "suspect" rather than "dead"
- If the project uses `__init__.py` re-exports, Vulture may flag them —
  check against actual import usage

**Ruff ERA tip:**

- ERA can false-positive on comments that _look_ like code but aren't
  (examples, pseudo-code, config-like lines). Ruff has a
  `lint.task-tags` config setting that can exclude TODO/FIXME/HACK
  lines from ERA detection — recommend adding it to `pyproject.toml` if
  false positives are frequent.
- See `references/stale-patterns.md` for the "when to flag vs ignore" table.

#### Optional: pre-commit / CI integration

For teams that want to **prevent** stale docs rather than just find them,
recommend these additions to the repo's config:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.11.0
    hooks:
      - id: ruff
        args: [--select, F401, F841, ERA, FIX]
  - repo: https://github.com/jshwi/docsig
    rev: v0.91.7
    hooks:
      - id: docsig
        args: [--check-class, --check-protected, --check-overridden]
  # Optional — docvet diff mode is fast enough for pre-commit:
  - repo: local
    hooks:
      - id: docvet-freshness
        name: docvet freshness
        entry: docvet check --freshness --staged
        language: system
        types: [python]
```

This catches the two most actionable categories before they ever hit the
repo: unused code (Ruff) and signature/docstring drift (docsig). docvet in
diff mode catches behavioral staleness on changed files.

---

### Tier 2 — Contextual analysis (model judgment)

These are the issues no linter catches. They require understanding what
the code does and what the docs say.

**Reference:** Read `references/stale-patterns.md` for before/after examples
of each pattern. It includes a severity table to help classify findings.

#### 0. Working-tree awareness (prerequisite)

Before scanning docstrings, check for uncommitted changes:

```bash
git diff HEAD --stat       # unstaged changes
git diff --cached --stat   # staged changes
```

For files with uncommitted changes: check **both** the committed version
(`git show HEAD:<file>`) and the working tree version for stale docs. A
function may have been cleaned up in the working tree while the committed
version still has the issue — report findings from committed code too.

For unchanged files: check only the working tree version.

**Why:** If a cleanup was already applied in uncommitted changes, the
findings still exist in the committed code for other developers. Flag them
but note "(already fixed in working tree)".

#### A. Stale fix-note docstrings

Docstrings that are _correct_ but read like release notes. Symptoms:

- "Fix: the original blueprint …" — this belongs in `git log`, not in `def`
- "Changed from X to Y because Z …" — describe current behavior, not the change
- Historical narrative in module docstrings (the module-level docstring is
  for _what the module does_, not _how it evolved_)

**Why this matters:** Every line of docstring is context you pay for on
every read. Historical notes push out information the next developer
actually needs — like what this function returns or what exceptions it
raises. AI coding agents read docstrings as ground truth about current
behavior; a narrative about what changed last month is noise at best and
misleading at worst.

**How to check:** For each function/module docstring containing
"Fix:", "original", "previously", "now", "changed from", "blueprint",
or version-like language — read it. If it describes _how the code got
this way_ rather than _what it does_, flag it as stale narrative.

#### B. Signature-docstring drift (automated by docsig, but deep-check here)

docsig catches parameter-level mismatches. But it won't catch:

- Return-type mismatch (`Returns:` says `str`, annotation says `int | None`)
- `Raises:` section referencing an exception no longer thrown
- Docstring says "returns a list of Users" but type says `list[dict]`
- Decorator-introduced behavior not documented (e.g., `@cached` not mentioned)

For these, inspect the function body and annotations, then compare against
the docstring's `Returns:` and `Raises:` sections.

#### C. Comments that lie or describe the wrong code

A comment explains what the code _should_ do or _used_ to do, not what it
_does_. Patterns:

- Comment says "fetch from cache, fall back to DB" but code hits the DB first
- Comment references a variable or function that was renamed
- Comment below a changed line that wasn't updated when the line was

**How to check:** For non-obvious inline comments, read the 3-5 lines of
code following the comment. If the comment and the code disagree, the
comment is stale.

#### D. Commented-out zombie code (beyond Ruff ERA)

Ruff ERA catches single-line zombie code (commented `import`, `print`, etc.).
But it can miss or only partially flag:

- Multi-block zombies: commented-out functions, entire `if`/`for` blocks
- Docstring-blocked code: a large comment block that contains code fragments
- Legacy code sections: "# Old approach (kept for reference)" — if it's been
  more than one release cycle, delete it

**How to check:** Scan for `# def `, `# class `, `# if `, `# for `, `# while `
at the start of comment lines, plus multi-line blocks spanned by `# ` with
indented code-like content inside.

#### E. TODO/FIXME/HACK without context (automated by Ruff FIX, needs judgment)

Ruff FIX collects all markers. Your job is to triage them:

| Pattern                                             | Action                                               |
| --------------------------------------------------- | ---------------------------------------------------- |
| `# TODO: fix this` — no explanation                 | Flag — needs context or delete                       |
| `# TODO(gh-123): add retry` next to code with retry | Flag — already done                                  |
| `# HACK: workaround for lib v2 bug (#456)`          | Keep — actionable and scoped                         |
| `# FIXME` — bare, next to complex logic             | Flag — what needs fixing?                            |
| `# OPTIMIZE: this is slow` — no metric              | Keep but note — vague unless paired with a benchmark |

Also: if the project references GitHub/GitLab issue numbers, check if
those issues are closed. If a TODO references a closed issue, the work
may already be done or the issue may have been resolved differently.

#### F. Pydantic / dataclass models defined but never used outside their module

Pydantic models and dataclasses are often defined but only referenced by
tests or never instantiated at all. Vulture can flag these, but it's
prone to false positives on model fields (which are accessed dynamically
via `model_validate`).

**How to check:**

1. Collect all `class X(BaseModel):` and `@dataclass` classes
2. For each, search the codebase for imports of that class outside its
   defining module (including `__init__.py` re-exports)
3. **Dead if:** imported nowhere, or imported but never instantiated/called
4. **Test-only if:** only imported in test files — flag as 🟡 medium and
   suggest either moving to a test utility module or documenting intent
5. **False positive if:** imported by `__init__.py` re-exports, used by
   framework magic (FastMCP decorators, Pydantic `model_validate`)

**Example:** `HistoryCommand(model.py:167)` is defined with `BaseModel` but
only imported by tests and never instantiated in production code. This is
test-only — safe to move or remove if tests don't need structured validation.

---

## Output format

Present findings grouped by severity, then by file:

```markdown
## Codebase Tidiness Report — src/

### 🔴 High (certain issues, safe to act on)

| File         | Line | Issue                                                     | Suggestion                   |
| ------------ | ---- | --------------------------------------------------------- | ---------------------------- |
| src/utils.py | 38   | `epoch_ms_to_datetime()` defined but never called         | Remove function              |
| src/cache.py | 13   | Docstring calls this "Full-text search" but uses SQL LIKE | Change to "Substring search" |

### 🟡 Medium (likely issues, verify first)

| File          | Line | Issue                                           | Suggestion                        |
| ------------- | ---- | ----------------------------------------------- | --------------------------------- |
| src/cache.py  | 131  | Fix-narrative docstring ("original blueprint…") | Trim to present-tense             |
| src/models.py | 73   | Vulture: `SILENT_SKIP_TYPES` — 60% confidence   | Verify not dynamically referenced |

### 🟢 Info (minor / tracking items)

| File          | Line | Issue                                                    | Suggestion            |
| ------------- | ---- | -------------------------------------------------------- | --------------------- |
| src/server.py | 100  | `# TODO: handle pagination` — no context                 | Add details or remove |
| src/loader.py | 1    | docsig: `load_jsonl_file` has undocumented param `cache` | Add to docstring      |
```

If the user asked for **fixing** as well as finding, append a second section:

```markdown
### Applied Fixes

- `src/utils.py:38` — Removed `epoch_ms_to_datetime()` (dead code)
- `src/cache.py:131` — Trimmed docstring to present tense
- `src/server.py:100` — Removed contextless TODO
```

---

## Report structure

1. **Summary** — how many files scanned, total findings, breakdown by tier
2. **High severity** — dead code, signature-docstring drifts, mislabeled docs
3. **Medium severity** — likely-stale narratives, possible dead code, stale docstrings without signature changes
4. **Info** — TODOs without context, minor nits, formatting nits
5. **Applied fixes** (only if user asked for fixes)

---

## Compatibility

- **Python codebases only** (Tier 1 tools are Python-specific)
- **Git repository** required for docvet freshness checks and Tier 2B drift detection
- **ruff**, **vulture**, **docsig** should be installed (the skill will attempt
  `uv add --dev <tool>` if missing, but defaults to running only available tools)
- **docvet** (optional) — adds git-aware stale docstring detection at two
  depth levels (fast diff mode for CI, slow drift mode for periodic sweeps)
- Existing Ruff configuration in `pyproject.toml` is respected — the skill
  appends `--select` flags rather than replacing config
