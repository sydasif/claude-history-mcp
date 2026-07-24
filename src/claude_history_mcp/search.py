"""Higher-level query functions on top of CacheManager, with date/filter support."""

import json
import logging
from datetime import UTC, datetime, timedelta

import dateparser

from .cache import CacheManager
from .utils import parse_timestamp

logger = logging.getLogger(__name__)


class SearchEngine:
    def __init__(self, cache: CacheManager):
        self.cache = cache

    def list_projects(self) -> list[dict]:
        """List all projects with metadata."""
        return self.cache.get_all_projects()

    def list_sessions(
        self,
        project: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """List sessions with optional filters."""
        sessions = self.cache.get_sessions(limit=limit * 2)  # overfetch for filtering

        if project:
            sessions = [
                s
                for s in sessions
                if project.lower()
                in (s.get("project_path", "") + s.get("display_name", "")).lower()
            ]

        if from_date or to_date:
            from_dt = (
                self._parse_natural_date(from_date, start_of_day=True)
                if from_date
                else None
            )
            to_dt = (
                self._parse_natural_date(to_date, end_of_day=True) if to_date else None
            )
            filtered = []
            for s in sessions:
                ts = parse_timestamp(s.get("last_timestamp"))
                if ts:
                    if from_dt and ts < from_dt:
                        continue
                    if to_dt and ts > to_dt:
                        continue
                filtered.append(s)
            sessions = filtered

        return sessions[:limit]

    def search_messages(
        self,
        query: str,
        project: str | None = None,
        session_id: str | None = None,
        role: str | None = None,
        tool_name: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Search messages with multiple filters."""
        project_id = None
        if project:
            projects = self.cache.get_all_projects()
            for p in projects:
                if (
                    project.lower()
                    in (p.get("project_path", "") + p.get("display_name", "")).lower()
                ):
                    project_id = p["id"]
                    break

        results = self.cache.search_messages(
            query=query,
            project_id=project_id,
            session_id=session_id,
            role=role,
            limit=limit * 3,
        )

        # Post-filter by tool_name and date (SQLite LIKE can't filter JSON tool_names)
        if tool_name:
            results = [
                r for r in results if tool_name in (r.get("tool_names", "") or "")
            ]
        if from_date or to_date:
            from_dt = (
                self._parse_natural_date(from_date, start_of_day=True)
                if from_date
                else None
            )
            to_dt = (
                self._parse_natural_date(to_date, end_of_day=True) if to_date else None
            )
            filtered = []
            for r in results:
                ts = parse_timestamp(r.get("timestamp"))
                if ts:
                    if from_dt and ts < from_dt:
                        continue
                    if to_dt and ts > to_dt:
                        continue
                    filtered.append(r)
                results = filtered

        # Transform results to include role and text_preview
        formatted_results = []
        for r in results:
            entry_type = r.get("entry_type")
            if entry_type == "user":
                role = "user"
            elif entry_type == "assistant":
                role = "assistant"
            elif entry_type == "system":
                role = "system"
            else:
                role = entry_type or "unknown"

            text = r.get("content_text", "")
            formatted_results.append({
                "session_id": r.get("session_id"),
                "project": r.get("project_path"),
                "timestamp": r.get("timestamp"),
                "role": role,
                "text_preview": text[:200] if text else "",
                "tool_names": json.loads(r.get("tool_names", "[]")) if r.get("tool_names") else [],
                "model": r.get("model"),
                "tokens_input": r.get("tokens_input", 0),
                "tokens_output": r.get("tokens_output", 0),
            })

        return formatted_results[:limit]

    def get_session(self, session_id: str) -> dict | None:
        """Get full session with messages."""
        session = self.cache.get_session(session_id)
        if not session:
            # Try prefix match
            sessions = self.cache.get_sessions(limit=1000)
            matches = [s for s in sessions if s["session_id"].startswith(session_id)]
            if len(matches) == 1:
                session = matches[0]
                session_id = matches[0]["session_id"]
            elif len(matches) > 1:
                # Ambiguous — return list of candidates so caller can disambiguate
                return {
                    "error": "ambiguous_prefix",
                    "candidates": [m["session_id"] for m in matches[:10]],
                }
        if not session:
            return None

        messages = self.cache.get_session_messages(session_id)
        # Transform messages to include role and text fields
        formatted_messages = []
        for msg in messages:
            role = msg.get("entry_type")
            if role == "user":
                role = "user"
            elif role == "assistant":
                role = "assistant"
            elif role == "system":
                role = "system"
            else:
                role = role or "unknown"

            text = msg.get("content_text", "")
            formatted_messages.append({
                "timestamp": msg.get("timestamp"),
                "role": role,
                "text": text,
                "tool_names": json.loads(msg.get("tool_names", "[]")) if msg.get("tool_names") else [],
                "model": msg.get("model"),
                "is_error": bool(msg.get("is_error")),
            })
        return {
            "session": session,
            "messages": formatted_messages,
        }

    def get_session_stats(self, session_id: str) -> dict | None:
        """Get token usage and tool statistics for a session."""
        session = self.cache.get_session(session_id)
        if not session:
            return None

        messages = self.cache.get_session_messages(session_id)
        tool_counts: dict[str, int] = {}
        models_used: set[str] = set()
        error_count = 0

        for msg in messages:
            if msg.get("tool_names"):
                try:
                    tools = json.loads(msg["tool_names"])
                    for t in tools:
                        tool_counts[t] = tool_counts.get(t, 0) + 1
                except Exception:
                    logger.exception("Failed to parse tool_names JSON")
            if msg.get("model"):
                models_used.add(msg["model"])
            if msg.get("is_error"):
                error_count += 1

        # Calculate duration
        duration_minutes: float = 0
        if session.get("first_timestamp") and session.get("last_timestamp"):
            first = parse_timestamp(session["first_timestamp"])
            last = parse_timestamp(session["last_timestamp"])
            if first and last:
                duration_minutes = round((last - first).total_seconds() / 60, 1)

        return {
            "session_id": session_id,
            "duration_minutes": duration_minutes,
            "total_input_tokens": session.get("total_input_tokens", 0),
            "total_output_tokens": session.get("total_output_tokens", 0),
            "message_count": session.get("message_count", 0),
            "tool_usage": dict(sorted(tool_counts.items(), key=lambda x: -x[1])),
            "models_used": sorted(models_used),
            "error_count": error_count,
        }

    def search_history(
        self,
        query: str,
        project: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Search the global command history."""
        results = self.cache.search_history(
            query=query, project=project, limit=limit * 2
        )

        if from_date or to_date:
            from_dt = (
                self._parse_natural_date(from_date, start_of_day=True)
                if from_date
                else None
            )
            to_dt = (
                self._parse_natural_date(to_date, end_of_day=True) if to_date else None
            )
            filtered = []
            for r in results:
                ts = datetime.fromtimestamp(r.get("timestamp_epoch", 0) / 1000, tz=UTC)
                if from_dt and ts < from_dt:
                    continue
                if to_dt and ts > to_dt:
                    continue
                filtered.append(r)
            results = filtered

        return results[:limit]

    def get_recent_activity(self, hours: int = 24, limit: int = 100) -> list[dict]:
        """Get recent messages across all projects. Timestamp-less entries always survive date filtering (spec 3.2)."""
        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=hours)
        cutoff_str = cutoff.isoformat()

        conn = self.cache.connect()
        rows = conn.execute(
            "SELECT m.*, p.project_path, p.display_name FROM messages m "
            "JOIN projects p ON m.project_id=p.id "
            "WHERE (m.timestamp >= ? OR m.timestamp IS NULL) AND m.entry_type IN ('user', 'assistant') "
            "ORDER BY (m.timestamp IS NULL) ASC, m.timestamp DESC LIMIT ?",
            (cutoff_str, limit),
        ).fetchall()

        # Transform to include role and text_preview
        formatted = []
        for r in rows:
            entry_type = r["entry_type"]
            if entry_type == "user":
                role = "user"
            elif entry_type == "assistant":
                role = "assistant"
            elif entry_type == "system":
                role = "system"
            else:
                role = entry_type or "unknown"

            text = r["content_text"] or ""
            formatted.append({
                "session_id": r["session_id"],
                "project": r["project_path"],
                "timestamp": r["timestamp"],
                "role": role,
                "text_preview": text[:200] if text else "",
                "tool_names": json.loads(r["tool_names"] or "[]"),
                "model": r["model"],
                "tokens_input": r["tokens_input"] or 0,
                "tokens_output": r["tokens_output"] or 0,
            })
        return formatted[:limit]

    def _parse_natural_date(
        self, date_str: str, start_of_day: bool = False, end_of_day: bool = False
    ) -> datetime | None:
        settings: dict[str, str | bool] = {
            "TIMEZONE": "UTC",
            "RETURN_AS_TIMEZONE_AWARE": False,
        }
        dt: datetime | None = dateparser.parse(date_str, settings=settings)
        if dt:
            # Ensure naive UTC datetime for comparison with parse_timestamp results
            if dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
            if start_of_day:
                dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
            if end_of_day:
                dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
        return dt