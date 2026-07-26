"""Higher-level query functions on top of CacheManager, with date/filter support."""

import json
import logging
from datetime import UTC, datetime, timedelta

import dateparser

from .cache import CacheManager
from .utils import calculate_cost, parse_timestamp

logger = logging.getLogger(__name__)


def _entry_type_to_role(entry_type: str | None) -> str:
    """Map entry_type to a role string."""
    if entry_type in ("user", "assistant", "system"):
        return entry_type
    return entry_type or "unknown"


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
        offset: int = 0,
    ) -> list[dict]:
        """List sessions with optional filters and pagination."""
        sessions = self.cache.get_sessions(
            limit=max(100, limit * 3)
        )  # overfetch for filtering

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

        return sessions[offset : offset + limit]

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
        offset: int = 0,
    ) -> list[dict]:
        """Search messages with multiple filters and pagination."""
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
            limit=max(100, (offset + limit) * 3),
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
            role_str = _entry_type_to_role(r.get("entry_type"))
            text = r.get("content_text", "")
            formatted_results.append(
                {
                    "session_id": r.get("session_id"),
                    "project": r.get("project_path"),
                    "timestamp": r.get("timestamp"),
                    "role": role_str,
                    "text_preview": text[:200] if text else "",
                    "tool_names": json.loads(r.get("tool_names", "[]"))
                    if r.get("tool_names")
                    else [],
                    "model": r.get("model"),
                    "tokens_input": r.get("tokens_input", 0),
                    "tokens_output": r.get("tokens_output", 0),
                }
            )

        return formatted_results[offset : offset + limit]

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
            role = _entry_type_to_role(msg.get("entry_type"))
            text = msg.get("content_text", "")
            formatted_messages.append(
                {
                    "timestamp": msg.get("timestamp"),
                    "role": role,
                    "text": text,
                    "tool_names": json.loads(msg.get("tool_names", "[]"))
                    if msg.get("tool_names")
                    else [],
                    "model": msg.get("model"),
                    "is_error": bool(msg.get("is_error")),
                }
            )
        return {
            "session": session,
            "messages": formatted_messages,
        }

    def get_session_stats(self, session_id: str) -> dict | None:
        """Get token usage and tool statistics for a session."""
        session = self.cache.get_session(session_id)
        if not session:
            # Try prefix match
            sessions = self.cache.get_sessions(limit=1000)
            matches = [s for s in sessions if s["session_id"].startswith(session_id)]
            if len(matches) == 1:
                session = matches[0]
                session_id = matches[0]["session_id"]
            elif len(matches) > 1:
                return {
                    "error": "ambiguous_prefix",
                    "candidates": [m["session_id"] for m in matches[:10]],
                }
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
            "total_input_tokens": session.get("total_input_tokens") or 0,
            "total_output_tokens": session.get("total_output_tokens") or 0,
            "message_count": session.get("message_count") or 0,
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
        offset: int = 0,
    ) -> list[dict]:
        """Search the global command history with pagination."""
        results = self.cache.search_history(
            query=query, project=project, limit=max(100, (offset + limit) * 2)
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

        return results[offset : offset + limit]

    def get_recent_activity(
        self, hours: int = 24, limit: int = 100, offset: int = 0
    ) -> list[dict]:
        """Get recent messages across all projects with pagination."""
        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=hours)
        cutoff_str = cutoff.isoformat()

        conn = self.cache.connect()
        rows = conn.execute(
            "SELECT m.*, p.project_path, p.display_name FROM messages m "
            "JOIN projects p ON m.project_id=p.id "
            "WHERE (m.timestamp >= ? OR m.timestamp IS NULL) AND m.entry_type IN ('user', 'assistant') "
            "ORDER BY (m.timestamp IS NULL) ASC, m.timestamp DESC LIMIT ?",
            (cutoff_str, offset + limit),
        ).fetchall()

        # Transform to include role and text_preview
        formatted = []
        for r in rows:
            role = _entry_type_to_role(r["entry_type"])
            text = r["content_text"] or ""
            formatted.append(
                {
                    "session_id": r["session_id"],
                    "project": r["project_path"],
                    "timestamp": r["timestamp"],
                    "role": role,
                    "text_preview": text[:200] if text else "",
                    "tool_names": json.loads(r["tool_names"] or "[]"),
                    "model": r["model"],
                    "tokens_input": r["tokens_input"] or 0,
                    "tokens_output": r["tokens_output"] or 0,
                }
            )
        return formatted[offset : offset + limit]

    def _resolve_project_id(self, project: str | None) -> int | None:
        if not project:
            return None
        projects = self.cache.get_all_projects()
        for p in projects:
            if (
                project.lower()
                in (p.get("project_path", "") + p.get("display_name", "")).lower()
            ):
                return int(p["id"])
        return None

    def get_cost_estimate(
        self, project: str | None = None, session_id: str | None = None
    ) -> dict:
        """Calculate total estimated cost in USD based on model and token counts."""
        project_id = self._resolve_project_id(project) if project else None
        rows = self.cache.get_cost_data(project_id=project_id, session_id=session_id)

        total_cost = 0.0
        total_input = 0
        total_output = 0
        model_costs: dict[str, float] = {}

        for r in rows:
            model = r.get("model") or "unknown"
            inp = r.get("tokens_input") or 0
            out = r.get("tokens_output") or 0
            total_input += inp
            total_output += out
            cost = calculate_cost(model, inp, out)
            total_cost += cost
            model_costs[model] = model_costs.get(model, 0.0) + cost

        return {
            "total_cost_usd": round(total_cost, 4),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "cost_by_model": {
                k: round(v, 4)
                for k, v in sorted(model_costs.items(), key=lambda x: -x[1])
            },
        }

    def get_model_usage(
        self,
        project: str | None = None,
        include_totals: bool = False,
        session_id: str | None = None,
    ) -> list[dict] | dict:
        """Get model breakdown with cost estimates."""
        project_id = self._resolve_project_id(project) if project else None

        if session_id:
            rows = self.cache.get_cost_data(
                project_id=project_id, session_id=session_id
            )
        else:
            rows = self.cache.get_model_usage(project_id=project_id)

        result = []
        total_cost = 0.0
        total_input = 0
        total_output = 0
        model_costs: dict[str, float] = {}

        for r in rows:
            # Handle both model_usage and cost_data structure
            model = r.get("model") or "unknown"
            inp = r.get("input_tokens") or r.get("tokens_input") or 0
            out = r.get("output_tokens") or r.get("tokens_output") or 0
            cost = calculate_cost(model, inp, out)

            if not session_id:
                result.append(
                    {
                        "model": model,
                        "message_count": r.get("message_count", 0),
                        "input_tokens": inp,
                        "output_tokens": out,
                        "estimated_cost_usd": round(cost, 4),
                    }
                )

            total_input += inp
            total_output += out
            total_cost += cost
            model_costs[model] = model_costs.get(model, 0.0) + cost

        if include_totals:
            return {
                "breakdown": result,
                "total_cost_usd": round(total_cost, 4),
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "cost_by_model": {
                    k: round(v, 4)
                    for k, v in sorted(model_costs.items(), key=lambda x: -x[1])
                },
            }
        return result

    def get_tool_usage(self, project: str | None = None) -> list[dict]:
        """Get tool frequency ranking."""
        project_id = self._resolve_project_id(project) if project else None
        return self.cache.get_tool_usage(project_id=project_id)

    # --- Project Tree ---
    def get_project_tree(
        self, project: str | None = None, limit_sessions: int = 50
    ) -> list[dict]:
        """Get hierarchical project→session→message tree view.

        Args:
            project: Optional project filter (partial match on path or display name)
            limit_sessions: Max sessions per project (default 50)

        Returns:
            List of projects with nested sessions and message summaries.
        """
        project_id = None
        if project:
            project_id = self._resolve_project_id(project)
        return self.cache.get_project_tree(
            project_id=project_id, limit_sessions=limit_sessions
        )

    # --- Project Stats (aggregated) ---
    def get_project_stats(
        self, project: str, detail_level: str = "full"
    ) -> dict | None:
        """Get aggregated statistics for a project.

        Args:
            project: Project path or display name (partial match)
            detail_level: "basic" or "full".
                - "basic": Returns only fields matching list_projects (id, project_path, display_name,
                  earliest_timestamp, latest_timestamp, total_messages, total_input_tokens, total_output_tokens)
                - "full": Returns all stats including session_count, unique_models, top_tools, etc.

        Returns:
            Dict with aggregated stats or None if not found.
        """
        project_id = self._resolve_project_id(project)
        if not project_id:
            return None

        conn = self.cache.connect()
        # Aggregate from projects table
        proj_row = conn.execute(
            "SELECT * FROM projects WHERE id=?", (project_id,)
        ).fetchone()
        if not proj_row:
            return None

        proj = dict(proj_row)

        # Session count
        session_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM sessions WHERE project_id=?", (project_id,)
        ).fetchone()["cnt"]

        # Date range from sessions
        date_range = conn.execute(
            "SELECT MIN(first_timestamp) as first_ts, MAX(last_timestamp) as last_ts "
            "FROM sessions WHERE project_id=?",
            (project_id,),
        ).fetchone()

        # Total tokens across all sessions
        token_sums = conn.execute(
            "SELECT COALESCE(SUM(total_input_tokens),0) as total_in, "
            "COALESCE(SUM(total_output_tokens),0) as total_out "
            "FROM sessions WHERE project_id=?",
            (project_id,),
        ).fetchone()

        if detail_level == "basic":
            return {
                "id": proj.get("id"),
                "project_path": proj.get("project_path"),
                "display_name": proj.get("display_name"),
                "earliest_timestamp": proj.get("earliest_timestamp"),
                "latest_timestamp": proj.get("latest_timestamp"),
                "total_messages": proj.get("total_messages", 0),
                "total_input_tokens": proj.get("total_input_tokens", 0),
                "total_output_tokens": proj.get("total_output_tokens", 0),
            }

        # Unique models used
        models = conn.execute(
            "SELECT DISTINCT model FROM messages WHERE project_id=? AND model IS NOT NULL",
            (project_id,),
        ).fetchall()

        # Top tools
        tool_rows = conn.execute(
            "SELECT tool_names FROM messages WHERE project_id=? AND tool_names IS NOT NULL AND tool_names != '[]'",
            (project_id,),
        ).fetchall()
        tool_counts: dict[str, int] = {}
        for r in tool_rows:
            try:
                tools = json.loads(r["tool_names"])
                for t in tools:
                    tool_counts[t] = tool_counts.get(t, 0) + 1
            except Exception:
                pass

        top_tools = sorted(tool_counts.items(), key=lambda x: -x[1])[:10]

        return {
            "project_path": proj.get("project_path"),
            "display_name": proj.get("display_name"),
            "session_count": session_count,
            "total_messages": proj.get("total_messages", 0),
            "total_input_tokens": token_sums["total_in"] if token_sums else 0,
            "total_output_tokens": token_sums["total_out"] if token_sums else 0,
            "first_session": date_range["first_ts"] if date_range else None,
            "last_session": date_range["last_ts"] if date_range else None,
            "unique_models": [m["model"] for m in models],
            "top_tools": [{"tool": k, "count": v} for k, v in top_tools],
            "estimated_cost_usd": 0.0,  # Could calculate from cache.get_cost_data
        }

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
