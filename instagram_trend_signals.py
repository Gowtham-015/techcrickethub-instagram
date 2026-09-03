import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Dict, List, Set
import requests

logger = logging.getLogger("InstagramTrendSignals")


class InstagramTrendSignalProvider:
    """Discovers real trending topics, keywords, and hashtags across Cricket, Tech, and Product Launches."""

    TREND_FEEDS = [
        "https://trends.google.com/trending/rss?geo=US",
        "https://trends.google.com/trending/rss?geo=IN",
    ]

    STATIC_CRICKET_TRENDS = {"cricket", "ipl", "t20", "test match", "bcci", "icc", "wicker", "century", "stadium"}
    STATIC_TECH_TRENDS = {"ai", "chatgpt", "openai", "silicon", "gpu", "apple", "google", "quantum", "android", "iphone"}

    def __init__(self, timeout: int = 8):
        self.timeout = timeout
        self._cached_trends: Set[str] = set()
        self._last_fetched: Optional[datetime] = None

    def fetch_current_trends(self) -> Set[str]:
        """Fetches live Google Trends RSS items and merges with domain trends."""
        now = datetime.now(timezone.utc)
        if self._last_fetched and (now - self._last_fetched).total_seconds() < 1800:
            return self._cached_trends

        trends: Set[str] = set(self.STATIC_CRICKET_TRENDS) | set(self.STATIC_TECH_TRENDS)
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

        for feed_url in self.TREND_FEEDS:
            try:
                resp = requests.get(feed_url, headers=headers, timeout=self.timeout)
                if resp.status_code == 200:
                    root = ET.fromstring(resp.content)
                    for item in root.findall(".//item"):
                        title = item.findtext("title")
                        if title:
                            clean_t = title.lower().strip()
                            trends.add(clean_t)
            except Exception as e:
                logger.debug(f"Trend RSS fetch error for {feed_url}: {e}")

        self._cached_trends = trends
        self._last_fetched = now
        logger.info(f"InstagramTrendSignalProvider updated: {len(trends)} active trend keywords.")
        return trends

    def score_trend_relevance(self, title: str, summary: str = "") -> float:
        """Scores candidate story trend relevance from 0.0 to 1.5."""
        if not title:
            return 1.0

        trends = self.fetch_current_trends()
        text = f"{title} {summary}".lower()

        match_count = 0
        matched_keywords = []

        for kw in trends:
            if len(kw) > 2 and re.search(r"\b" + re.escape(kw) + r"\b", text):
                match_count += 1
                matched_keywords.append(kw)

        if match_count == 0:
            return 1.0
        elif match_count == 1:
            logger.info(f"Trend signal boost (1.15x) for story '{title[:40]}...': matched '{matched_keywords[0]}'")
            return 1.15
        elif match_count == 2:
            logger.info(f"Trend signal boost (1.30x) for story '{title[:40]}...': matched {matched_keywords}")
            return 1.30
        else:
            logger.info(f"Trend signal boost (1.50x MAX) for story '{title[:40]}...': matched {matched_keywords[:3]}")
            return 1.50
