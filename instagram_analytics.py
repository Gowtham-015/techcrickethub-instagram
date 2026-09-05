import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from security import redact_token

VALID_EVENT_TYPES = {
    "DISCOVERED",
    "ACCEPTED",
    "REJECTED",
    "QUEUED",
    "SCHEDULED",
    "PROCESSING",
    "PUBLISHED",
    "FAILED",
    "SKIPPED",
    "DUPLICATE",
}


@dataclass
class InstagramAnalyticsEvent:
    """Represents a single granular Instagram publishing lifecycle analytics event."""

    event_id: str
    event_type: str
    content_id: Optional[str]
    timestamp: str
    category: str
    media_type: str
    content_score: int = 0
    priority: str = "NORMAL"
    scheduled_at: str = ""
    status: str = ""
    media_id: Optional[str] = None
    creation_id: Optional[str] = None
    error: Optional[str] = None

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if self.error:
            self.error = redact_token(self.error)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if d.get("error"):
            d["error"] = redact_token(d["error"])
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InstagramAnalyticsEvent":
        return cls(
            event_id=data.get("event_id") or str(uuid.uuid4()),
            event_type=str(data.get("event_type") or "DISCOVERED").upper(),
            content_id=data.get("content_id"),
            timestamp=data.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            category=str(data.get("category") or "cricket").lower(),
            media_type=str(data.get("media_type") or "IMAGE").upper(),
            content_score=int(data.get("content_score") or 0),
            priority=str(data.get("priority") or "NORMAL").upper(),
            scheduled_at=data.get("scheduled_at") or "",
            status=str(data.get("status") or "").upper(),
            media_id=data.get("media_id"),
            creation_id=data.get("creation_id"),
            error=redact_token(data.get("error")) if data.get("error") else None,
        )


class InstagramAnalyticsStore:
    """Persistent storage engine for Instagram analytics events in data/instagram_analytics.json."""

    def __init__(self, analytics_path: Optional[str] = None, retention_days: int = 90):
        if analytics_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            analytics_path = os.path.join(base_dir, "data", "instagram_analytics.json")

        self.analytics_path = analytics_path
        self.retention_days = retention_days
        self._ensure_file()

    def _ensure_file(self) -> None:
        """Ensures directory and JSON analytics file exist safely."""
        os.makedirs(os.path.dirname(self.analytics_path), exist_ok=True)
        if not os.path.exists(self.analytics_path):
            self._save({"events": []})
        else:
            try:
                data = self._load()
                if "events" not in data or not isinstance(data["events"], list):
                    self._save({"events": []})
            except Exception:
                self._save({"events": []})

    def _load(self) -> Dict[str, Any]:
        """Loads JSON analytics payload."""
        with open(self.analytics_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, data: Dict[str, Any]) -> None:
        """Atomic write to JSON analytics file."""
        temp_path = f"{self.analytics_path}.tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(temp_path, self.analytics_path)

    def record_event(self, event: InstagramAnalyticsEvent) -> InstagramAnalyticsEvent:
        """Records an analytics event with secret redaction and persistence."""
        data = self._load()
        events = data.get("events", [])
        events.append(event.to_dict())
        data["events"] = events
        self._save(data)
        return event

    def get_events(self, event_type: Optional[str] = None) -> List[InstagramAnalyticsEvent]:
        """Returns all recorded events, optionally filtered by event_type."""
        data = self._load()
        raw_events = data.get("events", [])
        events = [InstagramAnalyticsEvent.from_dict(e) for e in raw_events]

        if event_type:
            et_clean = event_type.upper()
            return [e for e in events if e.event_type == et_clean]
        return events

    def cleanup_old_events(self) -> int:
        """Removes events older than retention_days."""
        events = self.get_events()
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)

        fresh_events = []
        removed_count = 0

        for e in events:
            try:
                dt = datetime.fromisoformat(e.timestamp.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt >= cutoff:
                    fresh_events.append(e)
                else:
                    removed_count += 1
            except Exception:
                fresh_events.append(e)

        if removed_count > 0:
            self._save({"events": [e.to_dict() for e in fresh_events]})

        return removed_count

    def clear(self) -> None:
        """Clears all analytics events."""
        self._save({"events": []})


def record_performance_history(
    entry: Dict[str, Any],
    history_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Records a publication's performance data into data/performance_history.json."""
    if history_path is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        history_path = os.path.join(base_dir, "data", "performance_history.json")

    os.makedirs(os.path.dirname(history_path), exist_ok=True)

    history = []
    if os.path.exists(history_path):
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, list):
                    history = loaded
        except Exception:
            history = []

    clean_entry = {
        "media_id": entry.get("media_id") or entry.get("instagram_media_id") or "",
        "category": entry.get("category", "cricket"),
        "caption": entry.get("caption", ""),
        "published_at": entry.get("published_at") or datetime.now(timezone.utc).isoformat(),
        "source": entry.get("source") or entry.get("source_name") or "",
        "content_id": entry.get("content_id", ""),
        "permalink": entry.get("permalink") or entry.get("instagram_permalink") or "",
        "views": entry.get("views"),
        "likes": entry.get("likes"),
        "comments": entry.get("comments"),
        "shares": entry.get("shares"),
    }

    # Avoid duplicate media_id records
    history = [h for h in history if h.get("media_id") != clean_entry["media_id"] or not clean_entry["media_id"]]
    history.append(clean_entry)

    temp_path = f"{history_path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)
    os.replace(temp_path, history_path)
    return clean_entry


def get_performance_history(history_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves all records from data/performance_history.json."""
    if history_path is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        history_path = os.path.join(base_dir, "data", "performance_history.json")

    if not os.path.exists(history_path):
        return []

    try:
        with open(history_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []

