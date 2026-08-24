import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from config import Config
from instagram_cricket_data_provider import CricketMatch, FallbackCricketProvider, CricketDataProvider

logger = logging.getLogger("InstagramCricketMatchIntelligence")


@dataclass
class MatchIntelligenceSummary:
    state: str  # NO_MATCH, UPCOMING_MATCH, LIVE_MATCH, RECENTLY_COMPLETED_MATCH
    is_match_day: bool
    live_matches: List[CricketMatch] = field(default_factory=list)
    upcoming_matches: List[CricketMatch] = field(default_factory=list)
    completed_matches: List[CricketMatch] = field(default_factory=list)
    priority_multiplier: float = 1.0


class InstagramCricketMatchIntelligence:
    """Evaluates real cricket match states to trigger match-day priority overrides."""

    def __init__(self, provider: Optional[CricketDataProvider] = None, config: Optional[Config] = None):
        self.provider = provider or FallbackCricketProvider()
        self.config = config or Config.load_from_env(validate=False)

    def analyze_matches(self, matches: Optional[List[CricketMatch]] = None) -> MatchIntelligenceSummary:
        """Analyzes real match list and determines match state & priority multiplier."""
        match_list = matches if matches is not None else self.provider.get_live_and_upcoming_matches()

        live = [m for m in match_list if m.status == "LIVE"]
        upcoming = [m for m in match_list if m.status == "UPCOMING"]
        completed = [m for m in match_list if m.status == "COMPLETED"]

        is_match_day = len(live) > 0 or len(upcoming) > 0 or len(completed) > 0

        if live:
            state = "LIVE_MATCH"
            priority_mult = self.config.live_match_priority  # default 2.0
        elif upcoming:
            state = "UPCOMING_MATCH"
            priority_mult = self.config.match_day_cricket_priority  # default 1.5
        elif completed:
            state = "RECENTLY_COMPLETED_MATCH"
            priority_mult = self.config.match_day_cricket_priority  # default 1.5
        else:
            state = "NO_MATCH"
            priority_mult = 1.0

        logger.info(
            f"MatchIntelligence analysis: State '{state}', MatchDay: {is_match_day}, "
            f"Live: {len(live)}, Upcoming: {len(upcoming)}, Completed: {len(completed)}, Mult: {priority_mult}"
        )

        return MatchIntelligenceSummary(
            state=state,
            is_match_day=is_match_day,
            live_matches=live,
            upcoming_matches=upcoming,
            completed_matches=completed,
            priority_multiplier=priority_mult,
        )
