import json
import logging
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from instagram_content_bundle import ContentBundle
from security import redact_token

logger = logging.getLogger("InstagramContentAnalytics")


class InstagramContentAnalytics:
    """Persistent content analytics engine tracking published Instagram items and syncing real Meta Graph API insights.
    
    GUARANTEE: No synthetic, manufactured, or fake metrics are ever generated. All metrics originate strictly from Meta Graph API.
    """

    def __init__(self, analytics_file: Optional[str] = None):
        if analytics_file is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            analytics_file = os.path.join(base_dir, "data", "instagram_content_analytics.json")

        self.analytics_file = analytics_file
        self._ensure_file()

    def _ensure_file(self) -> None:
        """Ensures storage directory and analytics JSON file exist safely."""
        os.makedirs(os.path.dirname(self.analytics_file), exist_ok=True)
        if not os.path.exists(self.analytics_file):
            self._save_analytics({"items": [], "last_synced_at": None})
        else:
            try:
                data = self._load_analytics()
                if "items" not in data or not isinstance(data["items"], list):
                    self._save_analytics({"items": [], "last_synced_at": None})
            except Exception:
                self._save_analytics({"items": [], "last_synced_at": None})

    def _load_analytics(self) -> Dict[str, Any]:
        """Loads JSON analytics payload."""
        with open(self.analytics_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_analytics(self, data: Dict[str, Any]) -> None:
        """Atomic write to JSON analytics file."""
        temp_path = f"{self.analytics_file}.tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(temp_path, self.analytics_file)

    def record_published_item(
        self,
        bundle: ContentBundle,
        media_id: str,
        permalink: str = "",
        creation_id: str = "",
    ) -> Dict[str, Any]:
        """Records a real published Instagram Reel item into historical content analytics.
        
        Initializes real engagement counters to 0 until synced with Meta Graph API.
        """
        data = self._load_analytics()
        items: List[Dict[str, Any]] = data.get("items", [])
        now_iso = datetime.now(timezone.utc).isoformat()

        # Check if item already exists by media_id or content_id
        for existing in items:
            if existing.get("media_id") == media_id or existing.get("content_id") == bundle.content_id:
                existing["permalink"] = permalink or existing.get("permalink", "")
                existing["creation_id"] = creation_id or existing.get("creation_id", "")
                existing["updated_at"] = now_iso
                self._save_analytics(data)
                return existing

        topic = self._extract_topic(bundle.title, bundle.summary)

        new_entry = {
            "content_id": bundle.content_id,
            "media_id": media_id,
            "creation_id": creation_id,
            "title": bundle.title,
            "category": (bundle.category or "cricket").lower(),
            "topic": topic,
            "published_at": bundle.published_at or now_iso,
            "permalink": permalink,
            "media_type": (bundle.media_type or "REEL").upper(),
            "source_url": bundle.source_url or "",
            "media_url": bundle.media_url or "",
            "reach": 0,
            "views": 0,
            "likes": 0,
            "comments": 0,
            "shares": 0,
            "saves": 0,
            "engagement_rate": 0.0,
            "insights_synced": False,
            "created_at": now_iso,
            "updated_at": now_iso,
        }

        items.append(new_entry)
        data["items"] = items
        self._save_analytics(data)
        logger.info(f"Recorded published Reel '{bundle.title}' ({media_id}) in content analytics.")
        return new_entry

    def sync_meta_insights(self, access_token: Optional[str] = None, timeout: int = 10) -> Dict[str, Any]:
        """Syncs real Instagram engagement metrics (likes, comments, reach, views, shares, saves) via Meta Graph API.
        
        NOTE: Strictly uses official Meta Graph API data. If credentials/API are unavailable, preserves existing real data.
        """
        data = self._load_analytics()
        items: List[Dict[str, Any]] = data.get("items", [])
        synced_count = 0
        failed_count = 0

        if not access_token:
            logger.info("No Meta access token provided. Skipping Graph API live insights fetch.")
            return {"synced_count": 0, "failed_count": 0, "total_items": len(items)}

        now_iso = datetime.now(timezone.utc).isoformat()

        for item in items:
            media_id = item.get("media_id")
            if not media_id or media_id.startswith("mock_") or media_id.startswith("test_"):
                continue

            try:
                # 1. Query Media fields: like_count, comments_count, permalink
                fields_url = f"https://graph.facebook.com/v19.0/{media_id}?fields=like_count,comments_count,permalink&access_token={urllib.parse.quote(access_token)}"
                req = urllib.request.Request(fields_url, headers={"User-Agent": "TechCricketHub-Analytics/1.0"})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    if resp.getcode() == 200:
                        m_data = json.loads(resp.read().decode("utf-8"))
                        item["likes"] = int(m_data.get("like_count") or 0)
                        item["comments"] = int(m_data.get("comments_count") or 0)
                        if m_data.get("permalink"):
                            item["permalink"] = m_data.get("permalink")

                # 2. Query Media Insights: reach, plays, saved, shares
                insights_url = f"https://graph.facebook.com/v19.0/{media_id}/insights?metric=reach,plays,saved,shares&access_token={urllib.parse.quote(access_token)}"
                req_in = urllib.request.Request(insights_url, headers={"User-Agent": "TechCricketHub-Analytics/1.0"})
                with urllib.request.urlopen(req_in, timeout=timeout) as resp_in:
                    if resp_in.getcode() == 200:
                        in_data = json.loads(resp_in.read().decode("utf-8"))
                        for metric_obj in in_data.get("data", []):
                            name = metric_obj.get("name")
                            val = metric_obj.get("values", [{}])[0].get("value", 0) if metric_obj.get("values") else 0
                            if name == "reach":
                                item["reach"] = int(val)
                            elif name == "plays":
                                item["views"] = int(val)
                            elif name == "saved":
                                item["saves"] = int(val)
                            elif name == "shares":
                                item["shares"] = int(val)

                reach_val = max(int(item.get("reach") or 0), int(item.get("views") or 0), 1)
                total_eng = item["likes"] + item["comments"] + item["shares"] + item["saves"]
                item["engagement_rate"] = round((total_eng / reach_val) * 100.0, 2)
                item["insights_synced"] = True
                item["updated_at"] = now_iso
                synced_count += 1

            except Exception as e:
                logger.warning(f"Meta Graph API insights fetch error for media_id {media_id}: {redact_token(str(e))}")
                failed_count += 1

        data["last_synced_at"] = now_iso
        self._save_analytics(data)
        return {"synced_count": synced_count, "failed_count": failed_count, "total_items": len(items)}

    def get_analytics_summary(self) -> Dict[str, Any]:
        """Calculates aggregated performance statistics, category breakdown, and top-performing Reels."""
        data = self._load_analytics()
        items: List[Dict[str, Any]] = data.get("items", [])

        total_published = len(items)
        reel_count = sum(1 for it in items if it.get("media_type") == "REEL")
        cricket_count = sum(1 for it in items if it.get("category") == "cricket")
        tech_count = sum(1 for it in items if it.get("category") == "technology")

        total_likes = sum(int(it.get("likes") or 0) for it in items)
        total_comments = sum(int(it.get("comments") or 0) for it in items)
        total_reach = sum(int(it.get("reach") or 0) for it in items)
        total_views = sum(int(it.get("views") or 0) for it in items)
        total_shares = sum(int(it.get("shares") or 0) for it in items)
        total_saves = sum(int(it.get("saves") or 0) for it in items)

        avg_eng_rate = round(sum(float(it.get("engagement_rate") or 0.0) for it in items) / max(total_published, 1), 2)

        # Sort top Reels by engagement rate or views
        sorted_reels = sorted(items, key=lambda x: (float(x.get("engagement_rate") or 0.0), int(x.get("views") or 0)), reverse=True)
        top_reels = sorted_reels[:5]

        # Topic breakdown
        topics: Dict[str, int] = {}
        for it in items:
            t = it.get("topic") or "General"
            topics[t] = topics.get(t, 0) + 1

        return {
            "total_published": total_published,
            "reel_count": reel_count,
            "cricket_count": cricket_count,
            "tech_count": tech_count,
            "cricket_percentage": round((cricket_count / max(total_published, 1)) * 100.0, 1),
            "tech_percentage": round((tech_count / max(total_published, 1)) * 100.0, 1),
            "total_likes": total_likes,
            "total_comments": total_comments,
            "total_reach": total_reach,
            "total_views": total_views,
            "total_shares": total_shares,
            "total_saves": total_saves,
            "average_engagement_rate": avg_eng_rate,
            "topic_breakdown": topics,
            "top_performing_reels": top_reels,
            "last_synced_at": data.get("last_synced_at"),
        }

    @staticmethod
    def _extract_topic(title: str, summary: str) -> str:
        """Extracts a simple canonical topic keyword from title/summary."""
        text = f"{title} {summary}".lower()
        if "ipl" in text or "t20" in text:
            return "IPL & T20 Cricket"
        elif "bcci" in text or "india" in text or "team" in text:
            return "Indian Cricket News"
        elif "ai" in text or "artificial intelligence" in text or "model" in text:
            return "AI & Technology"
        elif "cricket" in text or "match" in text:
            return "General Cricket News"
        elif "tech" in text or "software" in text:
            return "General Tech News"
        return "General Updates"
