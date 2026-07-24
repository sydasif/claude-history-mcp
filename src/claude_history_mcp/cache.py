"""SQLite cache manager for parsed transcript entries, sessions, and projects.

Provides thread-safe CRUD operations with WAL mode and connection pooling.
"""

import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Generator

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
    return datetime.now(UTC).isoformat()


# Columns on the `sessions` table that upsert_session accepts via **kwargs.
# Unknown keys are silently skipped to prevent SQL injection via dynamic column names.
_ALLOWED_SESSION_COLUMNS: frozenset[str] = frozenset(
    {
        "summary",
        "ai_title",
        "first_timestamp",
        "last_timestamp",
        "message_count",
        "first_user_message",
        "cwd",
        "total_input_tokens",
        "total_output_tokens",
    }
)


class CacheManager:
    """Thread-safe SQLite cache manager for Claude Code session history.

    Provides CRUD operations for projects, sessions, messages, and command history.
    Uses WAL mode for concurrent access and connection pooling for performance.
    """

    def __init__(self, db_path: Path):
        """Initialize cache manager.

        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()

    def connect(self) -> sqlite3.Connection:
        """Get or create database connection with WAL mode enabled.

        Returns:
            SQLite connection with WAL mode, foreign keys, and row factory.
        """
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(SCHEMA)
        return self._conn

    def close(self) -> None:
        """Close database connection if open."""
        if self._conn:
            self._conn.close()
            self._conn = None

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for atomic database transactions.

        Yields:
            Database connection with automatic commit on success or rollback on error.
        """
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # --- Project CRUD ---
    def upsert_project(self, project_path: str, display_name: str) -> int:
        """Insert or update a project record.

        Args:
            project_path: Absolute path to the project directory.
            display_name: Human-readable project name.

        Returns:
            Database ID of the project.
        """
        conn = self.connect()
        with self._lock:
            conn.execute(
                "INSERT INTO projects (project_path, display_name, last_updated) VALUES (?, ?, ?) "
                "ON CONFLICT(project_path) DO UPDATE SET display_name=excluded.display_name, last_updated=excluded.last_updated",
                (project_path, display_name, _utcnow()),
            )
            conn.commit()
        row = conn.execute(
            "SELECT id FROM projects WHERE project_path=?", (project_path,)
        ).fetchone()
        return int(row["id"])

    def recompute_project_stats(self, project_id: int) -> None:
        """Roll session-level aggregates up to the parent project row.

        Args:
            project_id: ID of the project to recompute stats for.
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
        row = (
            self.connect()
            .execute("SELECT * FROM projects WHERE project_path=?", (project_path,))
            .fetchone()
        )
        return dict(row) if row else None

    def get_all_projects(self) -> list[dict]:
        rows = (
            self.connect()
            .execute("SELECT * FROM projects ORDER BY last_updated DESC")
            .fetchall()
        )
        return [dict(r) for r in rows]

    # --- Session CRUD ---
    def upsert_session(self, project_id: int, session_id: str, **kwargs: object) -> int:
        conn = self.connect()
        fields = ["project_id", "session_id"]
        values: list = [project_id, session_id]
        update_clauses = []
        for key, val in kwargs.items():
            if val is not None and key in _ALLOWED_SESSION_COLUMNS:
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
            "SELECT id FROM sessions WHERE project_id=? AND session_id=?",
            (project_id, session_id),
        ).fetchone()
        return int(row["id"])

    def get_sessions(
        self, project_id: int | None = None, limit: int = 100
    ) -> list[dict]:
        if project_id:
            rows = (
                self.connect()
                .execute(
                    "SELECT s.*, p.project_path, p.display_name FROM sessions s "
                    "JOIN projects p ON s.project_id=p.id WHERE s.project_id=? "
                    "ORDER BY s.last_timestamp DESC LIMIT ?",
                    (project_id, limit),
                )
                .fetchall()
            )
        else:
            rows = (
                self.connect()
                .execute(
                    "SELECT s.*, p.project_path, p.display_name FROM sessions s "
                    "JOIN projects p ON s.project_id=p.id "
                    "ORDER BY s.last_timestamp DESC LIMIT ?",
                    (limit,),
                )
                .fetchall()
            )
        return [dict(r) for r in rows]

    def get_session(self, session_id: str) -> dict | None:
        row = (
            self.connect()
            .execute(
                "SELECT s.*, p.project_path, p.display_name FROM sessions s "
                "JOIN projects p ON s.project_id=p.id WHERE s.session_id=?",
                (session_id,),
            )
            .fetchone()
        )
        return dict(row) if row else None

    # --- Message CRUD ---
    def insert_messages(
        self,
        project_id: int,
        session_id: str,
        file_name: str,
        entries: list[dict[str, object]],
    ) -> None:
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
        """Substring search across messages."""
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
        """Insert command history rows, ignoring duplicates via UNIQUE constraint."""
        conn = self.connect()
        cur = conn.executemany(
            "INSERT OR IGNORE INTO history_commands (display, project, session_id, timestamp_epoch) "
            "VALUES (?, ?, ?, ?)",
            [
                (c["display"], c["project"], c["sessionId"], c["timestamp"])
                for c in commands
            ],
        )
        conn.commit()
        return cur.rowcount if cur.rowcount is not None else 0

    def search_history(
        self, query: str, project: str | None = None, limit: int = 50
    ) -> list[dict]:
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
        row = (
            self.connect()
            .execute(
                "SELECT last_mtime FROM file_tracking WHERE file_path=?",
                (file_path,),
            )
            .fetchone()
        )
        return row["last_mtime"] if row else None

    def set_file_mtime(self, file_path: str, mtime: float) -> None:
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

    def clear_project_messages(
        self, project_id: int, session_id: str | None = None
    ) -> None:
        """Clear messages for a project/session (for reparse)."""
        conn = self.connect()
        if session_id:
            conn.execute(
                "DELETE FROM messages WHERE project_id=? AND session_id=?",
                (project_id, session_id),
            )
        else:
            conn.execute("DELETE FROM messages WHERE project_id=?", (project_id,))
        conn.commit()

    # --- Cache management ---
    # Order matters: child tables before parents for FK constraints.
    _TABLE_NAMES = (
        "messages",
        "sessions",
        "projects",
        "history_commands",
        "file_tracking",
    )

    def clear_all(self) -> None:
        conn = self.connect()
        for table in self._TABLE_NAMES:
            conn.execute(f"DELETE FROM {table}")  # noqa: S608 — table names from whitelist
        conn.commit()

    def get_stats(self) -> dict:
        conn = self.connect()
        return {
            "projects": conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0],
            "sessions": conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0],
            "messages": conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0],
            "history_commands": conn.execute(
                "SELECT COUNT(*) FROM history_commands"
            ).fetchone()[0],
        }
