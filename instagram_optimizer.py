from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from config import Config
from instagram_analytics import InstagramAnalyticsEvent
from instagram_category_analytics import InstagramCategoryAnalytics
from instagram_media_analytics import InstagramMediaAnalytics
from instagram_time_analytics import InstagramTimeAnalytics


@dataclass
class OptimizationRecommendation:
    """Represents conservative, data-backed publishing reliability recommendations."""

    category_recommendation: str
    media_recommendation: str
    time_recommendation: str
    score_recommendation: str
    confidence_status: str  # SUFFICIENT or INSUFFICIENT_DATA
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category_recommendation": self.category_recommendation,
            "media_recommendation": self.media_recommendation,
            "time_recommendation": self.time_recommendation,
            "score_recommendation": self.score_recommendation,
            "confidence_status": self.confidence_status,
            "details": self.details,
        }


class InstagramOptimizer:
    """Evaluates local publishing performance events and generates conservative, data-backed optimization recommendations."""

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config.load_from_env(validate=False)
        self.min_sample_size = self.config.analytics_min_sample_size

    def generate_recommendations(
        self,
        events: List[InstagramAnalyticsEvent],
    ) -> OptimizationRecommendation:
        """Analyzes recorded publishing events and produces conservative reliability recommendations."""
        total_events = len(events)

        if total_events < self.min_sample_size:
            return OptimizationRecommendation(
                category_recommendation="INSUFFICIENT_DATA: Collect more publishing events before adjusting category strategy.",
                media_recommendation="INSUFFICIENT_DATA: Maintain current balance between Images and Reels.",
                time_recommendation="INSUFFICIENT_DATA: Continue using standard posting windows (Asia/Kolkata).",
                score_recommendation=f"Prioritize content scores >= {self.config.content_score_threshold}.",
                confidence_status="INSUFFICIENT_DATA",
                details={"total_events": total_events, "min_sample_size": self.min_sample_size},
            )

        # 1. Category Analysis
        cat_stats = InstagramCategoryAnalytics.analyze_categories(events)
        best_cat = None
        best_cat_rate = -1.0
        for cat, stat in cat_stats.items():
            if stat.get("published", 0) + stat.get("failed", 0) >= 3:
                rate = stat.get("success_rate", 0.0)
                if rate > best_cat_rate:
                    best_cat_rate = rate
                    best_cat = cat.capitalize()

        cat_rec = (
            f"{best_cat} demonstrates highest publishing reliability ({best_cat_rate}% success). Maintain frequency."
            if best_cat
            else "Category publishing rates remain consistent across categories."
        )

        # 2. Media Analysis
        media_stats = InstagramMediaAnalytics.analyze_media(events)
        img_rate = media_stats.get("IMAGE", {}).get("success_rate", 0.0)
        reel_rate = media_stats.get("REEL", {}).get("success_rate", 0.0)

        if img_rate > reel_rate + 5.0:
            media_rec = "Images display higher container completion reliability. Do not increase Reel ratio prematurely."
        elif reel_rate > img_rate + 5.0:
            media_rec = "Reels container processing reliability is high. Maintain balanced mix."
        else:
            media_rec = "Images and Reels demonstrate comparable publishing reliability. Maintain balanced ratio."

        # 3. Time Analysis
        time_stats = InstagramTimeAnalytics.analyze_time_windows(events, tz_name=self.config.analytics_timezone)
        best_win = None
        best_win_rate = -1.0
        for w_key, stat in time_stats.items():
            rate = stat.get("success_rate", 0.0)
            if rate > best_win_rate:
                best_win_rate = rate
                best_win = stat.get("label", w_key)

        time_rec = (
            f"{best_win} demonstrates strongest publishing reliability ({best_win_rate}% success). Prefer window."
            if best_win
            else "Posting window success rates remain consistent across all windows."
        )

        score_rec = f"Prioritize content scores >= {self.config.content_score_threshold}."

        return OptimizationRecommendation(
            category_recommendation=cat_rec,
            media_recommendation=media_rec,
            time_recommendation=time_rec,
            score_recommendation=score_rec,
            confidence_status="SUFFICIENT",
            details={
                "total_events": total_events,
                "category_stats": cat_stats,
                "media_stats": media_stats,
                "time_stats": time_stats,
            },
        )

    def get_growth_recommendations(self, history_dir: Optional[str] = None) -> Dict[str, Any]:
        """Analyzes real engagement metrics (reach, saves, shares) to favor top-performing categories and time slots conservatively."""
        import json
        import os
        base_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = history_dir or os.path.join(base_dir, "data")
        eng_file = os.path.join(data_dir, "instagram_engagement_history.json")

        if not os.path.exists(eng_file):
            return {
                "confidence_status": "INSUFFICIENT_DATA",
                "message": "No engagement data recorded yet. Maintaining standard distribution.",
                "top_category": None,
                "top_format": None,
                "category_weights": {"cricket": 1.0, "technology": 1.0, "launches": 1.0},
            }

        try:
            with open(eng_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

        if len(data) < self.min_sample_size:
            return {
                "confidence_status": "INSUFFICIENT_DATA",
                "message": f"Collected {len(data)} engagement records (< {self.min_sample_size} required). Maintaining standard weights.",
                "total_records": len(data),
                "category_weights": {"cricket": 1.0, "technology": 1.0, "launches": 1.0},
            }

        cat_reach = {}
        for mid, metrics in data.items():
            cat = metrics.get("category", "cricket")
            reach = metrics.get("reach") or metrics.get("impressions") or 0
            if isinstance(reach, int):
                cat_reach[cat] = cat_reach.get(cat, 0) + reach

        best_cat = max(cat_reach, key=cat_reach.get) if cat_reach else "cricket"
        weights = {"cricket": 1.0, "technology": 1.0, "launches": 1.0, "geopolitics": 1.0, "democracy": 1.0, "entertainment": 1.0}
        weights[best_cat] = 1.15  # Conservative 15% boost for top reach category

        return {
            "confidence_status": "SUFFICIENT",
            "message": f"Growth feedback loop active: category '{best_cat}' yields highest total reach/engagement. Applying conservative 1.15x weight boost.",
            "top_category": best_cat,
            "category_weights": weights,
            "total_records": len(data),
        }
