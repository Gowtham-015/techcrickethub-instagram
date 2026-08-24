from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from zoneinfo import ZoneInfo
from instagram_analytics import InstagramAnalyticsEvent


class InstagramTimeAnalytics:
    """Aggregates publishing metrics and success rates by local IST posting windows."""

    WINDOWS: Dict[str, tuple[str, int, int]] = {
        "MORNING": ("08:00–10:00 IST", 8, 10),
        "AFTERNOON": ("13:00–15:00 IST", 13, 15),
        "EVENING": ("18:00–21:00 IST", 18, 21),
        "NIGHT": ("Off-Peak IST", 21, 8),
    }

    @classmethod
    def get_window_key(cls, dt_local: datetime) -> str:
        """Determines posting window key based on local hour."""
        hour = dt_local.hour
        if 8 <= hour < 10:
            return "MORNING"
        elif 13 <= hour < 15:
            return "AFTERNOON"
        elif 18 <= hour < 21:
            return "EVENING"
        else:
            return "NIGHT"

    @classmethod
    def analyze_time_windows(
        cls,
        events: List[InstagramAnalyticsEvent],
        tz_name: str = "Asia/Kolkata",
    ) -> Dict[str, Dict[str, Any]]:
        """Groups analytics events by local posting window and calculates metrics."""
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            if tz_name in ("Asia/Kolkata", "IST"):
                tz = timezone(timedelta(hours=5, minutes=30))
            else:
                tz = timezone.utc

        window_data: Dict[str, Dict[str, Any]] = {
            w_key: {
                "label": label,
                "scheduled_count": 0,
                "published_count": 0,
                "failed_count": 0,
            }
            for w_key, (label, _, _) in cls.WINDOWS.items()
        }

        for e in events:
            ts_str = e.timestamp or e.scheduled_at
            if not ts_str:
                continue

            try:
                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dt_local = dt.astimezone(tz)
                w_key = cls.get_window_key(dt_local)

                if e.event_type == "SCHEDULED":
                    window_data[w_key]["scheduled_count"] += 1
                elif e.event_type == "PUBLISHED":
                    window_data[w_key]["published_count"] += 1
                elif e.event_type == "FAILED":
                    window_data[w_key]["failed_count"] += 1
            except Exception:
                pass

        results: Dict[str, Dict[str, Any]] = {}
        for w_key, stats in window_data.items():
            pub = stats["published_count"]
            fail = stats["failed_count"]
            attempts = pub + fail
            success_rate = round((pub / attempts) * 100.0, 2) if attempts > 0 else 0.0

            results[w_key] = {
                "window": w_key,
                "label": stats["label"],
                "scheduled_count": stats["scheduled_count"],
                "published_count": pub,
                "failed_count": fail,
                "success_rate": success_rate,
            }

        return results
