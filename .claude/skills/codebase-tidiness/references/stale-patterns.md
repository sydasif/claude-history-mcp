# Stale Docstring & Comment Patterns

Reference examples for Tier 2 contextual analysis. Each shows the _bad_ pattern
(what to flag) and the _good_ alternative (what to suggest).

---

## Fix-narrative docstrings

### Bad — describes the change, not the behavior

```python
def recompute_project_stats(self, project_id: int) -> None:
    """Roll session-level aggregates up to the parent project row.

    Fix: the original blueprint exposed total_messages/total_input_tokens/
    total_output_tokens/earliest_timestamp/latest_timestamp on `projects`
    but nothing ever wrote to them, so list_projects() always reported
    zeros. This recomputes them from `sessions` after each load.
    """
```

### Good — describes what it does, present tense only

```python
def recompute_project_stats(self, project_id: int) -> None:
    """Roll session-level aggregates up to the parent project row."""
```

---

## Stale module docstring

### Bad — tells the origin story

```python
"""Shared utilities: surrogate handling, timestamp parsing, path helpers.

NOTE: This is the single source of truth for `parse_timestamp`. The original
blueprint defined it twice (once here, once in parser.py) — parser.py now
imports it from here instead of redefining it.
"""
```

### Good — states the module's purpose

```python
"""Shared utilities: surrogate handling, timestamp parsing, path helpers."""
```

---

## Re-export comment with historical note

### Bad — details the past bug

```python
# Re-exported so callers (e.g. loader.py) have one place to import
# parsing from; kept as a thin alias to avoid the duplicate-definition bug
# that existed in the original blueprint (parser.py and utils.py both defined
# parse_timestamp independently).
from .utils import parse_timestamp  # noqa: F401
```

### Good — states the current arrangement

```python
# Re-exported so callers (e.g. loader.py) have one place to import from.
from .utils import parse_timestamp  # noqa: F401
```

---

## Signature-docstring drift

### Bad — docstring lists obsolete parameters

```python
def connect(timeout: int = 30) -> Connection:
    """Connect to the database.

    Args:
        host: Database hostname
        port: Database port
        timeout: Connection timeout in seconds

    Returns:
        A Connection instance
    """
    # Only uses timeout now — host and port were moved to __init__
```

### Good — docstring matches signature

```python
def connect(timeout: int = 30) -> Connection:
    """Connect to the database.

    Args:
        timeout: Connection timeout in seconds

    Returns:
        A Connection instance
    """
```

---

## Wrong return type in docstring

### Bad — contradicts type annotation

```python
def lookup_user(user_id: int) -> User | None:
    """Look up a user by ID.

    Returns:
        User object
    """
    # Annotation says User | None, docstring says User
```

### Good — matches annotation

```python
def lookup_user(user_id: int) -> User | None:
    """Look up a user by ID.

    Returns:
        User object, or None if not found.
    """
```

---

## Comment that lies

### Bad — comment describes old behavior

```python
# Fetch from cache first, fall back to DB
result = db.query(...)  # No cache check happens
```

### Good — comment matches code, or removed if obvious

```python
# Fall back to DB if cache miss
cached = cache.get(key)
if cached:
    return cached
result = db.query(...)
```

---

## Contextless TODO

### Bad — no explanation

```python
# TODO: fix this
result = process(data)
```

### Good — has context

```python
# TODO: handle empty input gracefully — process() raises on None
result = process(data)
```

---

## Commented-out zombie code

### Bad — leftover from debugging

```python
def calculate(value):
    # result = old_calculate(value)
    # print("DEBUG:", result)
    return value * 2
```

### Good — deleted

_(just remove the commented lines)_

---

## When to flag vs ignore

| Pattern                                             | Flag?     | Why                                                                            |
| --------------------------------------------------- | --------- | ------------------------------------------------------------------------------ |
| "Fix: the original blueprint..."                    | 🔴 High   | Historical narrative in a function docstring                                   |
| "Note: this is the single source of truth..."       | 🟡 Medium | Module-level note about consolidation is useful info but belongs in commit msg |
| `# TODO: add retry` next to code with retry         | 🟡 Medium | Already done — remove TODO                                                     |
| `# This function does X` on a well-named function   | 🟢 Info   | Obvious comment, not harmful but unnecessary                                   |
| `# HACK: workaround for lib v2 bug` with ticket ref | ✅ Keep   | Legitimate context, actionable                                                 |
| Commented-out `import` from a refactor              | 🟡 Medium | Dead, but harmless if import not duplicated                                    |
