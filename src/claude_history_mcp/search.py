"""Higher-level query functions on top of CacheManager, with date/filter support."""

import json
import logging
from datetime import UTC, datetime

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
        sessions = self.cache.get_sessions(limit=offset + limit)

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
        project_id = self._resolve_project_id(project) if project else None

        from_dt = (
            self._parse_natural_date(from_date, start_of_day=True)
            if from_date
            else None
        )
        to_dt = self._parse_natural_date(to_date, end_of_day=True) if to_date else None

        results = self.cache.search_messages(
            query=query,
            project_id=project_id,
            session_id=session_id,
            role=role,
            tool_name=tool_name,
            from_date=from_dt.isoformat() if from_dt else None,
            to_date=to_dt.isoformat() if to_dt else None,
            limit=offset + limit,
        )

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

    def _resolve_session(self, session_id: str) -> dict | None:
        """Resolve a session by exact ID or unambiguous prefix (min 8 chars upstream).

        Returns the session dict, an {"error": "ambiguous_prefix", "candidates": [...]}
        dict if the prefix matches multiple sessions, or None if there's no match.
        """
        session = self.cache.get_session(session_id)
        if session:
            return session
        matches = self.cache.find_sessions_by_prefix(session_id, limit=11)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            return {
                "error": "ambiguous_prefix",
                "candidates": [m["session_id"] for m in matches[:10]],
            }
        return None

    def get_session(self, session_id: str) -> dict | None:
        """Get full session with messages."""
        session = self._resolve_session(session_id)
        if not session:
            return None
        if session.get("error") == "ambiguous_prefix":
            # Ambiguous — return list of candidates so caller can disambiguate
            return session
        session_id = session["session_id"]

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
            query=query, project=project, limit=offset + limit
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
