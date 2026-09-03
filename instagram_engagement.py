import json
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from instagram_client import InstagramAPIClient

logger = logging.getLogger("InstagramEngagement")


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
            "saved": None,
            "shares": None,
            "message": "Real Instagram API engagement metrics unavailable locally. No fake data generated.",
        }


class MetaGraphEngagementProvider(InstagramEngagementProvider):
    """Real Meta Graph API provider fetching actual per-post engagement & insights data."""

    def __init__(self, client: Optional[InstagramAPIClient] = None):
        self.client = client or InstagramAPIClient()

    def get_engagement_metrics(self, media_id: str) -> Dict[str, Any]:
        """Fetches real impressions, reach, likes, comments, saved, and shares from Meta Graph API."""
        if not media_id or not isinstance(media_id, str):
            return {
                "status": "ENGAGEMENT_DATA_UNAVAILABLE",
                "media_id": str(media_id),
                "message": "Invalid or missing media_id",
            }

        likes, comments, impressions, reach, saved, shares = None, None, None, None, None, None
        status = "PENDING"

        # 1. Fetch object fields (likes, comments)
        try:
            field_resp = self.client.get(f"{media_id}", params={"fields": "like_count,comments_count,timestamp"})
            if field_resp:
                likes = field_resp.get("like_count")
                comments = field_resp.get("comments_count")
        except Exception as fe:
            logger.debug(f"Media field fetch notice for {media_id}: {fe}")

        # 2. Fetch Insights metrics (impressions, reach, saved, shares)
        try:
            insights_resp = self.client.get(
                f"{media_id}/insights",
                params={"metric": "impressions,reach,saved,shares"},
            )
            data_list = insights_resp.get("data", []) if isinstance(insights_resp, dict) else []
            for item in data_list:
                name = item.get("name")
                val_data = item.get("values", [{}])[0].get("value")
                if name == "impressions":
                    impressions = val_data
                elif name == "reach":
                    reach = val_data
                elif name == "saved":
                    saved = val_data
                elif name == "shares":
                    shares = val_data

            if reach is not None or impressions is not None or likes is not None:
                status = "SUCCESS"
        except Exception as ie:
            logger.debug(f"Insights API notice for {media_id}: {ie}. Insights may be pending for recent media.")

        return {
            "status": status,
            "media_id": media_id,
            "likes": likes,
            "comments": comments,
            "impressions": impressions,
            "reach": reach,
            "saved": saved,
            "shares": shares,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }


def sync_recent_post_engagement(client: Optional[InstagramAPIClient] = None, days: int = 7, history_dir: Optional[str] = None) -> Dict[str, Any]:
    """Periodically fetches and persists real engagement metrics for posts published in the last N days."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = history_dir or os.path.join(base_dir, "data")
    os.makedirs(data_dir, exist_ok=True)

    pub_history_path = os.path.join(data_dir, "publish_history.json")
    eng_history_path = os.path.join(data_dir, "instagram_engagement_history.json")

    published_items = []
    if os.path.exists(pub_history_path):
        try:
            with open(pub_history_path, "r", encoding="utf-8") as f:
                pub_data = json.load(f)
                published_items = pub_data.get("published_items", [])
        except Exception:
            published_items = []

    provider = MetaGraphEngagementProvider(client=client)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    engagement_db = {}
    if os.path.exists(eng_history_path):
        try:
            with open(eng_history_path, "r", encoding="utf-8") as f:
                engagement_db = json.load(f)
        except Exception:
            engagement_db = {}

    synced_count = 0
    for item in published_items:
        media_id = item.get("media_id")
        pub_at_str = item.get("published_at")
        if not media_id:
            continue

        if pub_at_str:
            try:
                pub_dt = datetime.fromisoformat(pub_at_str.replace("Z", "+00:00"))
                if pub_dt < cutoff:
                    continue
            except Exception:
                pass

        metrics = provider.get_engagement_metrics(media_id)
        metrics["category"] = item.get("category", "cricket")
        metrics["media_type"] = item.get("media_type", "IMAGE")
        engagement_db[media_id] = metrics
        synced_count += 1

    temp_path = f"{eng_history_path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(engagement_db, f, indent=2)
    os.replace(temp_path, eng_history_path)

    logger.info(f"Engagement sync complete: updated metrics for {synced_count} recent posts.")
    return {"synced_count": synced_count, "total_records": len(engagement_db)}
