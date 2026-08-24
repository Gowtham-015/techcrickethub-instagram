from typing import Any, Dict, List
from instagram_analytics import InstagramAnalyticsEvent


class InstagramMediaAnalytics:
    """Aggregates publishing metrics and success rates by media type (IMAGE vs REEL)."""

    @classmethod
    def analyze_media(cls, events: List[InstagramAnalyticsEvent]) -> Dict[str, Dict[str, Any]]:
        """Groups analytics events by media_type and calculates per-media metrics."""
        media_data: Dict[str, Dict[str, Any]] = {
            "IMAGE": {"total": 0, "published": 0, "failed": 0, "scores": []},
            "REEL": {"total": 0, "published": 0, "failed": 0, "scores": []},
        }

        for e in events:
            mtype = (e.media_type or "IMAGE").upper()
            if mtype not in media_data:
                media_data[mtype] = {"total": 0, "published": 0, "failed": 0, "scores": []}

            if e.event_type in ("DISCOVERED", "QUEUED"):
                media_data[mtype]["total"] += 1
            elif e.event_type == "PUBLISHED":
                media_data[mtype]["published"] += 1
                if e.content_score > 0:
                    media_data[mtype]["scores"].append(e.content_score)
            elif e.event_type == "FAILED":
                media_data[mtype]["failed"] += 1

        results: Dict[str, Dict[str, Any]] = {}
        for mtype, stats in media_data.items():
            pub = stats["published"]
            fail = stats["failed"]
            attempts = pub + fail
            success_rate = round((pub / attempts) * 100.0, 2) if attempts > 0 else 0.0

            scores = stats["scores"]
            avg_score = round(sum(scores) / float(len(scores)), 1) if scores else 0.0

            results[mtype] = {
                "media_type": mtype,
                "total": stats["total"],
                "published": pub,
                "failed": fail,
                "success_rate": success_rate,
                "average_score": avg_score,
            }

        return results
