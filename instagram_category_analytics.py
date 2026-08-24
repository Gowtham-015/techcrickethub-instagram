from typing import Any, Dict, List
from instagram_analytics import InstagramAnalyticsEvent


class InstagramCategoryAnalytics:
    """Aggregates publishing metrics and success rates by category."""

    @classmethod
    def analyze_categories(cls, events: List[InstagramAnalyticsEvent]) -> Dict[str, Dict[str, Any]]:
        """Groups analytics events by category and calculates per-category metrics."""
        category_data: Dict[str, Dict[str, Any]] = {}

        for e in events:
            cat = (e.category or "unknown").lower()
            if cat not in category_data:
                category_data[cat] = {
                    "total_content": 0,
                    "accepted": 0,
                    "rejected": 0,
                    "published": 0,
                    "failed": 0,
                    "scores": [],
                }

            if e.event_type == "DISCOVERED":
                category_data[cat]["total_content"] += 1
            elif e.event_type == "ACCEPTED":
                category_data[cat]["accepted"] += 1
            elif e.event_type == "REJECTED":
                category_data[cat]["rejected"] += 1
            elif e.event_type == "PUBLISHED":
                category_data[cat]["published"] += 1
                if e.content_score > 0:
                    category_data[cat]["scores"].append(e.content_score)
            elif e.event_type == "FAILED":
                category_data[cat]["failed"] += 1

        results: Dict[str, Dict[str, Any]] = {}
        for cat, stats in category_data.items():
            pub = stats["published"]
            fail = stats["failed"]
            attempts = pub + fail
            success_rate = round((pub / attempts) * 100.0, 2) if attempts > 0 else 0.0

            scores = stats["scores"]
            avg_score = round(sum(scores) / float(len(scores)), 1) if scores else 0.0

            results[cat] = {
                "category": cat.capitalize(),
                "total_content": stats["total_content"],
                "accepted": stats["accepted"],
                "rejected": stats["rejected"],
                "published": pub,
                "failed": fail,
                "success_rate": success_rate,
                "average_score": avg_score,
            }

        return results
