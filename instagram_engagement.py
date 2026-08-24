from abc import ABC, abstractmethod
from typing import Any, Dict


class InstagramEngagementProvider(ABC):
    """Abstract interface for fetching real Instagram engagement metrics."""

    @abstractmethod
    def get_engagement_metrics(self, media_id: str) -> Dict[str, Any]:
        """Returns engagement metrics dictionary for a published media_id."""
        pass


class LocalEngagementProvider(InstagramEngagementProvider):
    """Local engagement provider safely returning ENGAGEMENT_DATA_UNAVAILABLE without fabricating fake data."""

    def get_engagement_metrics(self, media_id: str) -> Dict[str, Any]:
        """Returns explicit status indicating engagement data is unavailable locally."""
        return {
            "status": "ENGAGEMENT_DATA_UNAVAILABLE",
            "media_id": media_id,
            "likes": None,
            "comments": None,
            "impressions": None,
            "reach": None,
            "message": "Real Instagram API engagement metrics unavailable locally. No fake data generated.",
        }
