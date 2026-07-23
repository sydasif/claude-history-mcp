"""Higher-level query functions on top of CacheManager, with date/filter support."""

from datetime import datetime, timedelta, timezone

import dateparser

from .cache import CacheManager
from .utils import parse_timestamp


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
                if project.lower() in (s.get("project_path", "") + s.get("display_name", "")).lower()
            ]

        if from_date or to_date:
            from_dt = self._parse_natural_date(from_date, start_of_day=True) if from_date else None
            to_dt = self._parse_natural_date(to_date, end_of_day=True) if to_date else None
            filtered = []
            for s in sessions:
                ts = parse_timestamp(s.get("last_timestamp"))
                if ts:
                    if from_dt and ts < from_dt:
                        continue
                    if to_dt and ts > to_dt:
                        continue
                # Entries without timestamps always survive date filtering (spec 3.2)
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
                if project.lower() in (p.get("project_path", "") + p.get("display_name", "")).lower():
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
            results = [r for r in results if tool_name in (r.get("tool_names", "") or "")]
        if from_date or to_date:
            from_dt = self._parse_natural_date(from_date, start_of_day=True) if from_date else None
            to_dt = self._parse_natural_date(to_date, end_of_day=True) if to_date else None
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

        return results[:limit]

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
                return {"error": "ambiguous_prefix", "candidates": [m["session_id"] for m in matches[:10]]}
        if not session:
            return None

        messages = self.cache.get_session_messages(session_id)
        return {
            "session": session,
            "messages": messages,
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
                    import json

                    tools = json.loads(msg["tool_names"])
                    for t in tools:
                        tool_counts[t] = tool_counts.get(t, 0) + 1
                except Exception:
                    pass
            if msg.get("model"):
                models_used.add(msg["model"])
            if msg.get("is_error"):
                error_count += 1

        # Calculate duration
        duration_minutes = 0
        if session.get("first_timestamp") and session.get("last_timestamp"):
            first = parse_timestamp(session["first_timestamp"])
            last = parse_timestamp(session["last_timestamp"])
            if first and last:
                duration_minutes = round((last - first).total_seconds() / 60, 1)

        return {
            "session_id": session_id,
            "project": session.get("display_name"),
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
        """Search command history."""
        results = self.cache.search_history(query=query, project=project, limit=limit * 2)

        if from_date or to_date:
            from_dt = self._parse_natural_date(from_date, start_of_day=True) if from_date else None
            to_dt = self._parse_natural_date(to_date, end_of_day=True) if to_date else None
            filtered = []
            for r in results:
                ts = datetime.fromtimestamp(r.get("timestamp_epoch", 0) / 1000)
                if from_dt and ts < from_dt:
                    continue
                if to_dt and ts > to_dt:
                    continue
                filtered.append(r)
            results = filtered

        return results[:limit]

    def get_recent_activity(self, hours: int = 24) -> list[dict]:
        """Get recent messages across all projects.

        Fix: the original blueprint filtered with `WHERE m.timestamp >= ?`,
        which in SQL silently drops rows where timestamp IS NULL (NULL
        comparisons are neither true nor false). Spec 3.2 requires
        timestamp-less entries to always survive date filtering, so those
        rows are now included and sorted after the timestamped ones.
        """
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)
        cutoff_str = cutoff.isoformat()

        conn = self.cache.connect()
        rows = conn.execute(
            "SELECT m.*, p.project_path, p.display_name FROM messages m "
            "JOIN projects p ON m.project_id=p.id "
            "WHERE (m.timestamp >= ? OR m.timestamp IS NULL) AND m.entry_type IN ('user', 'assistant') "
            "ORDER BY (m.timestamp IS NULL) ASC, m.timestamp DESC LIMIT 100",
            (cutoff_str,),
        ).fetchall()
        return [dict(r) for r in rows]

    def _parse_natural_date(
        self, date_str: str, start_of_day: bool = False, end_of_day: bool = False
    ) -> datetime | None:
        settings = {"TIMEZONE": "UTC", "RETURN_AS_TIMEZONE_AWARE": False}
        dt = dateparser.parse(date_str, settings=settings)
        if dt and start_of_day:
            dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        if dt and end_of_day:
            dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
        return dt
