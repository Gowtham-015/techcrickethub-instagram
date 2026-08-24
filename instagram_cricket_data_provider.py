import logging
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import requests

from security import redact_token

logger = logging.getLogger("CricketDataProvider")


@dataclass
class CricketMatch:
    """Structured representation of a real cricket match."""

    match_id: str
    series: str
    team_a: str
    team_b: str
    start_time: str  # ISO timestamp or descriptive time
    status: str  # UPCOMING, LIVE, COMPLETED, NO_MATCH
    source: str
    venue: str = ""
    result: str = ""
    score_details: str = ""
    raw_metadata: Dict[str, Any] = field(default_factory=dict)


class CricketDataProvider(ABC):
    """Abstract interface for fetching real cricket match data."""

    @abstractmethod
    def get_live_and_upcoming_matches(self) -> List[CricketMatch]:
        """Returns list of real cricket matches."""
        pass


class CricAPICricketProvider(CricketDataProvider):
    """Fetches real match data from CricAPI v1."""

    def __init__(self, api_url: str = "https://api.cricapi.com/v1", api_key: str = "", timeout: int = 10):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def get_live_and_upcoming_matches(self) -> List[CricketMatch]:
        if not self.api_key:
            logger.info("CricAPI key not provided. Skipping CricAPI provider.")
            return []

        endpoint = f"{self.api_url}/currentMatches?apikey={self.api_key}&offset=0"
        try:
            resp = requests.get(endpoint, timeout=self.timeout)
            if resp.status_code != 200:
                logger.warning(f"CricAPI HTTP {resp.status_code}: {redact_token(resp.text)}")
                return []

            data = resp.json()
            if data.get("status") != "success" or "data" not in data:
                logger.warning(f"CricAPI returned non-success: {data.get('reason', 'unknown')}")
                return []

            matches = []
            for item in data.get("data", []):
                match_id = str(item.get("id", ""))
                teams = item.get("teams", [])
                team_a = teams[0] if len(teams) > 0 else item.get("name", "Team A").split(" vs ")[0]
                team_b = teams[1] if len(teams) > 1 else "Team B"
                series = item.get("series_id", item.get("name", "Cricket Series"))
                status_raw = str(item.get("status", "")).upper()

                match_status = "UPCOMING"
                if "LIVE" in status_raw or item.get("matchStarted"):
                    match_status = "LIVE"
                if item.get("matchEnded"):
                    match_status = "COMPLETED"

                matches.append(
                    CricketMatch(
                        match_id=f"cricapi-{match_id}",
                        series=series,
                        team_a=team_a,
                        team_b=team_b,
                        start_time=item.get("dateTimeGMT", datetime.now(timezone.utc).isoformat()),
                        status=match_status,
                        venue=item.get("venue", ""),
                        result=item.get("status", ""),
                        score_details=str(item.get("score", "")),
                        source="CricAPI",
                        raw_metadata=item,
                    )
                )
            return matches

        except Exception as e:
            logger.warning(f"Error fetching from CricAPI: {redact_token(str(e))}")
            return []


class PublicRSSCricketProvider(CricketDataProvider):
    """Fetches real cricket news & score updates from public RSS feeds."""

    def __init__(self, rss_url: str = "https://www.espncricinfo.com/rss/content/story/feeds/0.xml", timeout: int = 10):
        self.rss_url = rss_url
        self.timeout = timeout

    def get_live_and_upcoming_matches(self) -> List[CricketMatch]:
        if not self.rss_url:
            return []

        try:
            resp = requests.get(self.rss_url, timeout=self.timeout)
            if resp.status_code != 200:
                logger.warning(f"Cricket RSS HTTP {resp.status_code}")
                return []

            root = ET.fromstring(resp.content)
            items = root.findall(".//item")
            matches = []

            for idx, item in enumerate(items[:10]):
                title = item.findtext("title", "")
                link = item.findtext("link", "")
                pub_date = item.findtext("pubDate", "")
                desc = item.findtext("description", "")

                if not title or not link:
                    continue

                status = "COMPLETED"
                if "vs" in title.lower():
                    status = "LIVE" if ("live" in title.lower() or "in progress" in desc.lower()) else "UPCOMING"

                # Parse teams if vs in title
                teams = title.split(" vs ")
                team_a = teams[0] if len(teams) > 0 else title
                team_b = teams[1] if len(teams) > 1 else ""

                matches.append(
                    CricketMatch(
                        match_id=f"rss-cricket-{idx}-{hash(link) & 0xffffffff}",
                        series="Cricket Highlights",
                        team_a=team_a,
                        team_b=team_b,
                        start_time=pub_date or datetime.now(timezone.utc).isoformat(),
                        status=status,
                        venue="",
                        result=desc[:150] if desc else title,
                        source="ESPNCricinfo RSS",
                        raw_metadata={"link": link, "title": title, "description": desc},
                    )
                )
            return matches

        except Exception as e:
            logger.warning(f"Error fetching Cricket RSS: {redact_token(str(e))}")
            return []


class FallbackCricketProvider(CricketDataProvider):
    """Chains multiple real providers gracefully. NEVER returns fake match data."""

    def __init__(self, providers: Optional[List[CricketDataProvider]] = None):
        self.providers = providers or [
            CricAPICricketProvider(),
            PublicRSSCricketProvider(),
        ]

    def get_live_and_upcoming_matches(self) -> List[CricketMatch]:
        for provider in self.providers:
            try:
                matches = provider.get_live_and_upcoming_matches()
                if matches:
                    return matches
            except Exception as e:
                logger.warning(f"Provider {provider.__class__.__name__} failed: {e}")

        logger.info("No real match data returned from any provider.")
        return []
