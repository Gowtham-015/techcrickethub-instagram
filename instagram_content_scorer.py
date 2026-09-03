from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from instagram_media_metadata import MediaAsset
from instagram_pipeline import InstagramContent


@dataclass
class ContentScore:
    """Represents deterministic content score and breakdown."""

    total_score: int
    priority_label: str
    decision: str
    breakdown: Dict[str, int] = field(default_factory=dict)
    explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_score": self.total_score,
            "priority_label": self.priority_label,
            "decision": self.decision,
            "breakdown": self.breakdown,
            "explanation": self.explanation,
        }


class InstagramContentScorer:
    """Evaluates Instagram content quality, media availability, category relevance,

    freshness, and engagement potential yielding a deterministic score from 0–100.
    """

    def __init__(self, score_threshold: int = 35):
        self.score_threshold = score_threshold

    def score_content(
        self,
        content: InstagramContent,
        asset: Optional[MediaAsset] = None,
    ) -> ContentScore:
        """Calculates deterministic quality score from 0 to 100 with detailed breakdown."""
        title = (content.title or "").strip()
        summary = (content.summary or "").strip()
        category = (content.category or "").strip().lower()
        media_url = content.image_url if content.media_type == "IMAGE" else content.video_url

        # 1. Title Quality (max 20 points)
        title_score = 0
        if title:
            words = len(title.split())
            if 5 <= words <= 25:
                title_score = 20
            elif 3 <= words < 5 or 25 < words <= 35:
                title_score = 14
            else:
                title_score = 8

        # 2. Summary Quality (max 20 points)
        summary_score = 0
        if summary:
            summary_words = len(summary.split())
            if 15 <= summary_words <= 60:
                summary_score = 20
            elif 8 <= summary_words < 15 or 60 < summary_words <= 100:
                summary_score = 14
            else:
                summary_score = 8

        # 3. Category Relevance (max 20 points)
        category_score = 0
        known_categories = {"cricket", "technology", "ai", "sports", "entertainment"}
        if category in known_categories:
            category_score = 20
        elif category:
            category_score = 12

        # 4. Media Quality & Availability (max 20 points)
        media_score = 0
        if media_url and media_url.startswith("https://"):
            media_score = 15
            if asset and asset.status_code == 200:
                media_score = 20

        # 5. Freshness & Completeness (max 20 points)
        completeness_score = 0
        if content.source:
            completeness_score += 5
        if content.caption:
            completeness_score += 5
        if title and summary and media_url:
            completeness_score += 10

        total = title_score + summary_score + category_score + media_score + completeness_score

        # 6. Trend Signal Boost Factor (up to 1.5x multiplier)
        trend_mult = 1.0
        if hasattr(self, "trend_provider") and self.trend_provider:
            try:
                trend_mult = self.trend_provider.score_trend_relevance(title, summary)
            except Exception:
                trend_mult = 1.0

        trend_boost_points = int(round(total * (trend_mult - 1.0)))
        total = max(0, min(100, total + trend_boost_points))

        # Classify priority
        if total >= 90:
            priority = "CRITICAL"
        elif total >= 75:
            priority = "HIGH"
        elif total >= 55:
            priority = "NORMAL"
        elif total >= 35:
            priority = "LOW"
        else:
            priority = "REJECT"

        decision = "ACCEPT" if total >= self.score_threshold and priority != "REJECT" else "REJECT"

        breakdown = {
            "title_quality": title_score,
            "summary_quality": summary_score,
            "category_relevance": category_score,
            "media_quality": media_score,
            "completeness": completeness_score,
            "trend_boost": trend_boost_points,
        }

        explanation = (
            f"Total score: {total}/100. Title: {title_score}/20, Summary: {summary_score}/20, "
            f"Category: {category_score}/20, Media: {media_score}/20, Completeness: {completeness_score}/20, "
            f"Trend Boost: +{trend_boost_points} (mult {trend_mult:.2f}x). Decision: {decision} ({priority})."
        )

        return ContentScore(
            total_score=total,
            priority_label=priority,
            decision=decision,
            breakdown=breakdown,
            explanation=explanation,
        )
