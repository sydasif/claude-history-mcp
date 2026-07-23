"""SQLite cache layer for parsed transcript entries, sessions, and projects."""

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY,
    project_path TEXT UNIQUE NOT NULL,
    display_name TEXT,
    earliest_timestamp TEXT,
    latest_timestamp TEXT,
    total_messages INTEGER DEFAULT 0,
    total_input_tokens INTEGER DEFAULT 0,
    total_output_tokens INTEGER DEFAULT 0,
    last_updated TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
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

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),
    session_id TEXT NOT NULL,
    file_name TEXT NOT NULL,
    entry_type TEXT NOT NULL,
    timestamp TEXT,
    uuid TEXT,
    parent_uuid TEXT,
    is_sidechain INTEGER DEFAULT 0,
    content_text TEXT,
    tool_names TEXT,
    model TEXT,
    tokens_input INTEGER DEFAULT 0,
    tokens_output INTEGER DEFAULT 0,
    is_error INTEGER DEFAULT 0,
    raw_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS history_commands (
    id INTEGER PRIMARY KEY,
    display TEXT NOT NULL,
    project TEXT,
    session_id TEXT,
    timestamp_epoch INTEGER,
    UNIQUE(display, project, session_id, timestamp_epoch)
);

CREATE TABLE IF NOT EXISTS file_tracking (
    file_path TEXT PRIMARY KEY,
    last_mtime REAL,
    last_loaded TEXT
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_type ON messages(entry_type);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_messages_text ON messages(content_text);
CREATE INDEX IF NOT EXISTS idx_messages_project ON messages(project_id);
CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_id);
CREATE INDEX IF NOT EXISTS idx_history_project ON history_commands(project);
"""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class CacheManager:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(SCHEMA)
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    @contextmanager
    def transaction(self):
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # --- Project CRUD ---
    def upsert_project(self, project_path: str, display_name: str) -> int:
        conn = self.connect()
        with self._lock:
            conn.execute(
                "INSERT INTO projects (project_path, display_name, last_updated) VALUES (?, ?, ?) "
                "ON CONFLICT(project_path) DO UPDATE SET display_name=excluded.display_name, last_updated=excluded.last_updated",
                (project_path, display_name, _utcnow()),
            )
            conn.commit()
        row = conn.execute("SELECT id FROM projects WHERE project_path=?", (project_path,)).fetchone()
        return row["id"]

    def recompute_project_stats(self, project_id: int) -> None:
        """Roll session-level aggregates up to the parent project row.

        Fix: the original blueprint exposed total_messages/total_input_tokens/
        total_output_tokens/earliest_timestamp/latest_timestamp on `projects`
        but nothing ever wrote to them, so list_projects() always reported
        zeros. This recomputes them from `sessions` after each load.
        """
        conn = self.connect()
        row = conn.execute(
            "SELECT COALESCE(SUM(message_count), 0) AS total_messages, "
            "COALESCE(SUM(total_input_tokens), 0) AS total_input_tokens, "
            "COALESCE(SUM(total_output_tokens), 0) AS total_output_tokens, "
            "MIN(first_timestamp) AS earliest_timestamp, "
            "MAX(last_timestamp) AS latest_timestamp "
            "FROM sessions WHERE project_id=?",
            (project_id,),
        ).fetchone()
        conn.execute(
            "UPDATE projects SET total_messages=?, total_input_tokens=?, total_output_tokens=?, "
            "earliest_timestamp=?, latest_timestamp=?, last_updated=? WHERE id=?",
            (
                row["total_messages"],
                row["total_input_tokens"],
                row["total_output_tokens"],
                row["earliest_timestamp"],
                row["latest_timestamp"],
                _utcnow(),
                project_id,
            ),
        )
        conn.commit()

    def get_project(self, project_path: str) -> dict | None:
        row = self.connect().execute("SELECT * FROM projects WHERE project_path=?", (project_path,)).fetchone()
        return dict(row) if row else None

    def get_all_projects(self) -> list[dict]:
        rows = self.connect().execute("SELECT * FROM projects ORDER BY last_updated DESC").fetchall()
        return [dict(r) for r in rows]

    # --- Session CRUD ---
    def upsert_session(self, project_id: int, session_id: str, **kwargs) -> int:
        conn = self.connect()
        fields = ["project_id", "session_id"]
        values: list = [project_id, session_id]
        update_clauses = []
        for key, val in kwargs.items():
            if val is not None:
                fields.append(key)
                values.append(val)
                update_clauses.append(f"{key}=excluded.{key}")
        placeholders = ",".join(["?"] * len(values))
        field_str = ",".join(fields)
        if update_clauses:
            update_str = ",".join(update_clauses)
            conn.execute(
                f"INSERT INTO sessions ({field_str}) VALUES ({placeholders}) "
                f"ON CONFLICT(project_id, session_id) DO UPDATE SET {update_str}",
                values,
            )
        else:
            conn.execute(
                f"INSERT OR IGNORE INTO sessions ({field_str}) VALUES ({placeholders})",
                values,
            )
        conn.commit()
        row = conn.execute(
            "SELECT id FROM sessions WHERE project_id=? AND session_id=?", (project_id, session_id)
        ).fetchone()
        return row["id"]

    def get_sessions(self, project_id: int | None = None, limit: int = 100) -> list[dict]:
        if project_id:
            rows = self.connect().execute(
                "SELECT s.*, p.project_path, p.display_name FROM sessions s "
                "JOIN projects p ON s.project_id=p.id WHERE s.project_id=? "
                "ORDER BY s.last_timestamp DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
        else:
            rows = self.connect().execute(
                "SELECT s.*, p.project_path, p.display_name FROM sessions s "
                "JOIN projects p ON s.project_id=p.id "
                "ORDER BY s.last_timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_session(self, session_id: str) -> dict | None:
        row = self.connect().execute(
            "SELECT s.*, p.project_path, p.display_name FROM sessions s "
            "JOIN projects p ON s.project_id=p.id WHERE s.session_id=?",
            (session_id,),
        ).fetchone()
        return dict(row) if row else None

    # --- Message CRUD ---
    def insert_messages(self, project_id: int, session_id: str, file_name: str, entries: list[dict]):
        """Insert parsed entries into messages table."""
        conn = self.connect()
        conn.executemany(
            "INSERT INTO messages (project_id, session_id, file_name, entry_type, timestamp, "
            "uuid, parent_uuid, is_sidechain, content_text, tool_names, model, tokens_input, "
            "tokens_output, is_error, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    project_id,
                    session_id,
                    file_name,
                    e["entry_type"],
                    e["timestamp"],
                    e["uuid"],
                    e.get("parent_uuid"),
                    e.get("is_sidechain", 0),
                    e.get("content_text", ""),
                    e.get("tool_names", ""),
                    e.get("model", ""),
                    e.get("tokens_input", 0),
                    e.get("tokens_output", 0),
                    e.get("is_error", 0),
                    e["raw_json"],
                )
                for e in entries
            ],
        )
        conn.commit()

    def search_messages(
        self,
        query: str,
        project_id: int | None = None,
        session_id: str | None = None,
        role: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Full-text search across messages.

        Fix: the original blueprint wrote this as two adjacent top-level
        string statements (`sql = "..."` followed by a bare `"..."` on the
        next line) instead of one concatenated string or a `+`-joined
        expression. That second line is a no-op statement in Python, so the
        query silently lost its JOIN and WHERE clause and would raise
        `no such column: p.project_path` on every call.
        """
        sql = (
            "SELECT m.*, p.project_path, p.display_name FROM messages m "
            "JOIN projects p ON m.project_id=p.id WHERE m.content_text LIKE ?"
        )
        params: list = [f"%{query}%"]
        if project_id:
            sql += " AND m.project_id=?"
            params.append(project_id)
        if session_id:
            sql += " AND m.session_id=?"
            params.append(session_id)
        if role:
            sql += " AND m.entry_type=?"
            params.append(role)
        sql += " ORDER BY m.timestamp DESC LIMIT ?"
        params.append(limit)
        return [dict(r) for r in self.connect().execute(sql, params).fetchall()]

    def get_session_messages(self, session_id: str) -> list[dict]:
        """Get all messages for a session in order."""
        return [
            dict(r)
            for r in self.connect()
            .execute(
                "SELECT * FROM messages WHERE session_id=? ORDER BY id ASC",
                (session_id,),
            )
            .fetchall()
        ]

    # --- History CRUD ---
    def insert_history_commands(self, commands: list[dict]) -> int:
        """Insert command history rows, ignoring exact duplicates.

        Fix: original schema had no uniqueness constraint and `initialize()`
        reloads history.jsonl on every startup (it's append-only, not
        mtime-tracked), so every restart re-inserted the entire file. The
        UNIQUE(display, project, session_id, timestamp_epoch) constraint plus
        INSERT OR IGNORE here makes reloading idempotent.
        """
        conn = self.connect()
        cur = conn.executemany(
            "INSERT OR IGNORE INTO history_commands (display, project, session_id, timestamp_epoch) "
            "VALUES (?, ?, ?, ?)",
            [(c["display"], c["project"], c["sessionId"], c["timestamp"]) for c in commands],
        )
        conn.commit()
        return cur.rowcount if cur.rowcount is not None else 0

    def search_history(self, query: str, project: str | None = None, limit: int = 50) -> list[dict]:
        sql = "SELECT * FROM history_commands WHERE display LIKE ?"
        params: list = [f"%{query}%"]
        if project:
            sql += " AND project LIKE ?"
            params.append(f"%{project}%")
        sql += " ORDER BY timestamp_epoch DESC LIMIT ?"
        params.append(limit)
        return [dict(r) for r in self.connect().execute(sql, params).fetchall()]

    # --- File mtime tracking (cache invalidation) ---
    def get_file_mtime(self, file_path: str) -> float | None:
        row = self.connect().execute(
            "SELECT last_mtime FROM file_tracking WHERE file_path=?",
            (file_path,),
        ).fetchone()
        return row["last_mtime"] if row else None

    def set_file_mtime(self, file_path: str, mtime: float):
        conn = self.connect()
        conn.execute(
            "INSERT OR REPLACE INTO file_tracking (file_path, last_mtime, last_loaded) VALUES (?, ?, ?)",
            (file_path, mtime, _utcnow()),
        )
        conn.commit()

    def get_changed_files(self, file_paths: list[Path]) -> list[Path]:
        """Return files whose mtime differs from cached (or that aren't cached yet)."""
        changed = []
        for fp in file_paths:
            current_mtime = fp.stat().st_mtime
            cached_mtime = self.get_file_mtime(str(fp))
            if cached_mtime is None or abs(current_mtime - cached_mtime) >= 1.0:
                changed.append(fp)
        return changed

    def clear_project_messages(self, project_id: int, session_id: str | None = None):
        """Clear messages for a project/session (for reparse)."""
        conn = self.connect()
        if session_id:
            conn.execute("DELETE FROM messages WHERE project_id=? AND session_id=?", (project_id, session_id))
        else:
            conn.execute("DELETE FROM messages WHERE project_id=?", (project_id,))
        conn.commit()

    # --- Cache management ---
    def clear_all(self):
        conn = self.connect()
        for table in ["messages", "sessions", "projects", "history_commands", "file_tracking"]:
            conn.execute(f"DELETE FROM {table}")
        conn.commit()

    def get_stats(self) -> dict:
        conn = self.connect()
        return {
            "projects": conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0],
            "sessions": conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0],
            "messages": conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0],
            "history_commands": conn.execute("SELECT COUNT(*) FROM history_commands").fetchone()[0],
        }
