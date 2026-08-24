import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import requests

from config import Config
from instagram_content_source import InstagramContentSource
from security import redact_token

logger = logging.getLogger("InstagramRealNewsSource")


class InstagramRealNewsSource(InstagramContentSource):
    """Production real news source acquiring authentic Cricket and Tech news from verified RSS feeds."""

    def __init__(
        self,
        config: Optional[Config] = None,
        timeout: int = 10,
    ):
        self.config = config or Config.load_from_env(validate=False)
        self.timeout = timeout
        self.cricket_feeds = [
            f.strip()
            for f in self.config.cricket_rss_feeds.split(",")
            if f.strip()
        ]
        self.tech_feeds = [
            f.strip()
            for f in self.config.tech_rss_feeds.split(",")
            if f.strip()
        ]

    @staticmethod
    def generate_stable_id(url: str, source_name: str) -> str:
        """Generates a stable, SHA256-based content ID for production items."""
        clean_url = (url or "").strip().lower()
        hasher = hashlib.sha256(f"{source_name}:{clean_url}".encode("utf-8"))
        return f"real-{hasher.hexdigest()[:16]}"

    @staticmethod
    def parse_rss_date(date_str: Optional[str]) -> Optional[datetime]:
        """Parses common RSS pubDate formats into timezone-aware datetime."""
        if not date_str or not isinstance(date_str, str):
            return None
        date_clean = date_str.strip()

        formats = [
            "%a, %d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S GMT",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(date_clean, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                pass
        return None

    def fetch_feed_items(self, feed_url: str, category: str) -> List[Dict[str, Any]]:
        """Fetches and parses articles from a single RSS feed URL."""
        if not feed_url:
            return []

        try:
            headers = {"User-Agent": "TechCricketHubInstagramAutomation/1.0"}
            resp = requests.get(feed_url, headers=headers, timeout=self.timeout)
            if resp.status_code != 200:
                logger.warning(f"RSS feed HTTP {resp.status_code} for {redact_token(feed_url)}")
                return []

            root = ET.fromstring(resp.content)
            items = root.findall(".//item")
            results = []
            now = datetime.now(timezone.utc)

            max_age_hours = (
                self.config.max_cricket_news_age_hours
                if category == "cricket"
                else self.config.max_tech_news_age_hours
            )

            source_domain = feed_url.split("/")[2] if "//" in feed_url else feed_url

            for item in items[:15]:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                description = (item.findtext("description") or "").strip()
                pub_date_str = item.findtext("pubDate") or item.findtext("dc:date")

                # Remove HTML tags from description
                clean_desc = re.sub(r"<[^>]+>", "", description).strip()

                if not title or not link:
                    continue

                pub_dt = self.parse_rss_date(pub_date_str) or now
                age_hours = (now - pub_dt).total_seconds() / 3600.0

                # Reject stale content
                if age_hours > max_age_hours:
                    logger.info(f"Skipping stale {category} article ({int(age_hours)}h old): '{title}'")
                    continue

                # Extract image url from enclosure, media tags, or img src in description
                image_url = None
                enclosure = item.find("enclosure")
                if enclosure is not None:
                    enc_url = enclosure.get("url", "")
                    enc_type = enclosure.get("type", "")
                    if "image" in enc_type or enc_url.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                        image_url = enc_url

                if not image_url:
                    namespaces = {"media": "http://search.yahoo.com/mrss/"}
                    for media_tag in ("media:content", "media:thumbnail"):
                        media_elem = item.find(media_tag, namespaces)
                        if media_elem is not None and media_elem.get("url"):
                            image_url = media_elem.get("url")
                            break

                if not image_url and description:
                    img_match = re.search(r'<img[^>]+src=["\'](https?://[^"\']+)["\']', description, re.IGNORECASE)
                    if img_match:
                        image_url = img_match.group(1)

                # Fallback: Authentic Category Match Image (Cricket Stadium / Tech Banner)
                if not image_url or "pbYX4gp_5kE" in image_url:
                    if category == "cricket":
                        image_url = "https://images.unsplash.com/photo-1540747913346-19e32dc3e97e?q=80&w=1080&auto=format&fit=crop"
                    else:
                        image_url = "https://images.unsplash.com/photo-1518770660439-4636190af475?q=80&w=1080&auto=format&fit=crop"

                content_id = self.generate_stable_id(link, source_domain)

                results.append(
                    {
                        "content_id": content_id,
                        "title": title,
                        "summary": clean_desc[:250] if clean_desc else title,
                        "category": category,
                        "source_name": source_domain,
                        "source_url": link,
                        "published_at": pub_dt.isoformat(),
                        "collected_at": now.isoformat(),
                        "content_type": "NEWS",
                        "media_type": "IMAGE",
                        "image_url": image_url,
                        "video_url": None,
                    }
                )

            return results

        except Exception as e:
            logger.warning(f"Error reading RSS feed {redact_token(feed_url)}: {redact_token(str(e))}")
            return []

    def get_content_items(self) -> List[Dict[str, Any]]:
        """Collects real Cricket and Tech news items across all configured RSS sources."""
        all_items: List[Dict[str, Any]] = []

        # 1. Fetch Cricket feeds
        for feed in self.cricket_feeds:
            items = self.fetch_feed_items(feed, category="cricket")
            all_items.extend(items)

        # 2. Fetch Tech feeds
        for feed in self.tech_feeds:
            items = self.fetch_feed_items(feed, category="technology")
            all_items.extend(items)

        logger.info(f"RealNewsSource acquired {len(all_items)} verified articles from RSS feeds.")
        return all_items
