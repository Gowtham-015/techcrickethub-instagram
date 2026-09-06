import logging
import math
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from config import Config
from instagram_cricket_balancer import InstagramCricketBalancer, BalanceMetrics
from instagram_cricket_match_intelligence import InstagramCricketMatchIntelligence, MatchIntelligenceSummary
from instagram_media_metadata import MediaAsset
from instagram_pipeline import InstagramContent, InstagramContentNormalizer

logger = logging.getLogger("InstagramContentIntelligence")


STOP_WORDS: Set[str] = {
    "a", "an", "the", "in", "on", "at", "to", "for", "of", "with", "and", "or",
    "is", "are", "was", "were", "be", "been", "by", "from", "as", "it", "this",
    "that", "its", "has", "have", "had", "will", "would", "about", "after", "over",
}

TIER1_DOMAINS: Set[str] = {
    "bbc.com", "espncricinfo.com", "cricbuzz.com", "ndtv.com", "icc-cricket.com", "reuters.com", "bbc.co.uk",
}
TIER2_DOMAINS: Set[str] = {
    "techcrunch.com", "wired.com", "theverge.com", "engadget.com", "arstechnica.com", "gsmarena.com",
    "timesofindia.indiatimes.com", "variety.com",
}

MAJOR_TOURNAMENTS: List[str] = [
    "world cup", "asia cup", "ipl", "t20 world cup", "champions trophy",
    "border-gavaskar", "ashes", "wtc", "world test championship", "bbl", "psl",
]

FINALS_KEYWORDS: List[str] = [
    "final", "finals", "semi-final", "semifinal", "trophy match", "championship final", "title clash",
]

PLAYER_ANNOUNCEMENT_KEYWORDS: List[str] = [
    "retirement", "retires", "retired", "captain", "squad", "contract", "bcci",
    "appointed", "head coach", "injury update", "steps down", "named captain",
]

BREAKING_CRICKET_KEYWORDS: List[str] = [
    "breaking", "historic victory", "historic win", "record", "century", "hat-trick",
    "win over", "triumph", "thriller", "stunning win", "unbelievable finish",
]


@dataclass
class CandidateScore:
    """Detailed score report for a single candidate item."""

    candidate_id: str
    title: str
    category: str
    media_type: str
    source_domain: str
    published_at: str
    video_available: bool
    media_rights_status: str
    total_score: int
    freshness_score: int
    importance_score: int
    source_reliability_score: int
    video_score: int
    category_priority_score: int
    cluster_penalty: int
    is_high_priority_cricket: bool
    is_event_duplicate: bool
    explanation: str
    raw_item: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "title": self.title,
            "category": self.category,
            "media_type": self.media_type,
            "source_domain": self.source_domain,
            "published_at": self.published_at,
            "video_available": self.video_available,
            "media_rights_status": self.media_rights_status,
            "total_score": self.total_score,
            "freshness_score": self.freshness_score,
            "importance_score": self.importance_score,
            "source_reliability_score": self.source_reliability_score,
            "video_score": self.video_score,
            "category_priority_score": self.category_priority_score,
            "cluster_penalty": self.cluster_penalty,
            "is_high_priority_cricket": self.is_high_priority_cricket,
            "is_event_duplicate": self.is_event_duplicate,
            "explanation": self.explanation,
            "raw_item": self.raw_item,
        }


class EventClusterer:
    """Detects event similarity and clustering to prevent posting redundant articles on the same event."""

    @staticmethod
    def tokenize(text: str) -> Set[str]:
        if not text:
            return set()
        words = re.findall(r"\b[a-z0-9]+\b", text.lower())
        return {w for w in words if w not in STOP_WORDS and len(w) > 2}

    def calculate_similarity(self, title1: str, title2: str) -> float:
        t1 = self.tokenize(title1)
        t2 = self.tokenize(title2)
        if not t1 or not t2:
            return 0.0
        intersection = len(t1.intersection(t2))
        union = len(t1.union(t2))
        return intersection / union if union > 0 else 0.0

    def check_event_cooldown(
        self, candidate_title: str, published_history: List[Dict[str, Any]], similarity_threshold: float = 0.45
    ) -> Tuple[bool, float, str]:
        """Checks if candidate matches a recently published item (within last 10 items / 24h)."""
        if not candidate_title or not published_history:
            return False, 0.0, ""

        cand_tokens = self.tokenize(candidate_title)
        if not cand_tokens:
            return False, 0.0, ""

        recent_items = published_history[-15:] if len(published_history) > 15 else published_history

        for item in reversed(recent_items):
            prev_title = item.get("title") or item.get("caption") or ""
            if not prev_title:
                continue

            sim = self.calculate_similarity(candidate_title, prev_title)
            if sim >= similarity_threshold:
                return True, round(sim, 2), prev_title

        return False, 0.0, ""


class FreshnessScorer:
    """Evaluates time-decay freshness based on published_at timestamp."""

    @staticmethod
    def parse_timestamp(timestamp_str: str) -> Optional[datetime]:
        if not timestamp_str:
            return None
        clean_ts = timestamp_str.strip()
        try:
            if clean_ts.endswith("Z"):
                clean_ts = clean_ts[:-1] + "+00:00"
            return datetime.fromisoformat(clean_ts)
        except Exception:
            pass

        for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%a, %d %b %Y %H:%M:%S %z"]:
            try:
                return datetime.strptime(timestamp_str, fmt)
            except Exception:
                continue
        return None

    def calculate_freshness_score(self, published_at: str) -> int:
        dt = self.parse_timestamp(published_at)
        if not dt:
            return 60  # Default reasonable score when timestamp is omitted

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        age_hours = (now - dt).total_seconds() / 3600.0

        if age_hours < 0:
            return 100
        elif age_hours <= 2.0:
            return 100
        elif age_hours <= 6.0:
            return 85
        elif age_hours <= 12.0:
            return 70
        elif age_hours <= 24.0:
            return 50
        elif age_hours <= 48.0:
            return 35
        else:
            return 20


class SourceReliabilityScorer:
    """Evaluates source domain reputation score."""

    def calculate_source_score(self, source_domain: str) -> int:
        if not source_domain:
            return 50
        domain_clean = source_domain.lower().strip()
        for d in TIER1_DOMAINS:
            if d in domain_clean:
                return 100
        for d in TIER2_DOMAINS:
            if d in domain_clean:
                return 85
        return 70


class CricketPriorityEngine:
    """Evaluates cricket high-priority triggers (live matches, major tournaments, finals, player announcements, breaking news)."""

    def __init__(self, match_intelligence: Optional[InstagramCricketMatchIntelligence] = None):
        self.match_intel = match_intelligence or InstagramCricketMatchIntelligence()

    def evaluate_cricket_priority(
        self, title: str, summary: str, category: str
    ) -> Tuple[bool, float, List[str]]:
        if category.lower() != "cricket":
            return False, 1.0, []

        text = f"{title} {summary}".lower()
        triggers = []

        # Check match intelligence state
        match_summary = self.match_intel.analyze_matches()
        if match_summary.state == "LIVE_MATCH":
            triggers.append("LIVE_MATCH")
        elif match_summary.state in ["UPCOMING_MATCH", "RECENTLY_COMPLETED_MATCH"]:
            triggers.append("MATCH_DAY")

        # Check text keyword triggers
        for tournament in MAJOR_TOURNAMENTS:
            if tournament in text:
                triggers.append(f"TOURNAMENT:{tournament.upper()}")
                break

        for final_kw in FINALS_KEYWORDS:
            if final_kw in text:
                triggers.append(f"FINAL:{final_kw.upper()}")
                break

        for player_kw in PLAYER_ANNOUNCEMENT_KEYWORDS:
            if player_kw in text:
                triggers.append(f"ANNOUNCEMENT:{player_kw.upper()}")
                break

        for breaking_kw in BREAKING_CRICKET_KEYWORDS:
            if breaking_kw in text:
                triggers.append(f"BREAKING:{breaking_kw.upper()}")
                break

        is_high_priority = len(triggers) > 0

        multiplier = 1.0
        if "LIVE_MATCH" in triggers:
            multiplier = 2.0
        elif is_high_priority:
            multiplier = 1.5

        return is_high_priority, multiplier, triggers


class ContentIntelligenceEngine:
    """Production-safe Content Intelligence & Cricket Priority Engine.

    Enforces 75% Cricket / 25% Tech ratio over rolling 30 window,
    prevents technology starvation, prioritizes high-stakes cricket events,
    clusters duplicate events, scores candidates across multi-factor matrix,
    and enforces 100% Reel video requirements (0% image fallback).
    """

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config.load_from_env(validate=False)
        self.cricket_balancer = InstagramCricketBalancer(config=self.config)
        self.freshness_scorer = FreshnessScorer()
        self.source_scorer = SourceReliabilityScorer()
        self.event_clusterer = EventClusterer()
        self.cricket_priority_engine = CricketPriorityEngine()
        self.normalizer = InstagramContentNormalizer()

    def evaluate_and_rank_candidates(
        self, raw_candidates: List[Dict[str, Any]], published_history: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Evaluates, scores, and ranks candidate content items.

        Returns structured report containing rolling window balance metrics and ranked candidate list.
        """
        if not raw_candidates:
            return {
                "balance_metrics": self.cricket_balancer.evaluate_balance(published_history).to_dict() if hasattr(self.cricket_balancer.evaluate_balance(published_history), "to_dict") else vars(self.cricket_balancer.evaluate_balance(published_history)),
                "ranked_candidates": [],
                "top_candidate": None,
                "status": "NO_CANDIDATES",
            }

        balance = self.cricket_balancer.evaluate_balance(published_history)
        scored_candidates: List[CandidateScore] = []

        for item in raw_candidates:
            content = self.normalizer.normalize(item)
            content_id = (content.metadata or {}).get("content_id") or item.get("content_id") or "unknown"
            title = content.title or item.get("title") or ""
            summary = content.summary or item.get("summary") or ""
            category = (content.category or item.get("category") or "cricket").strip().lower()
            media_type = (content.media_type or item.get("media_type") or "REEL").upper()
            source_domain = getattr(content, "source_domain", "") or item.get("source_domain") or ""
            published_at = getattr(content, "published_at", "") or item.get("published_at") or ""
            rights_status = item.get("media_rights_status", "RIGHTS_EVIDENCE_MISSING")

            media_url = content.video_url if media_type == "REEL" else content.image_url
            has_valid_video = media_type == "REEL" and bool(media_url) and media_url.startswith("http")

            # 1. Video Availability Score (Max 20 pts; 0 if image-only or missing video)
            video_score = 20 if has_valid_video else 0

            # 2. Freshness Score (Max 20 pts)
            fresh_score = self.freshness_scorer.calculate_freshness_score(published_at)

            # 3. Source Reliability Score (Max 15 pts)
            source_rel = self.source_scorer.calculate_source_score(source_domain)
            source_score = int(round(source_rel * 0.15))

            # 4. Importance & Priority Score (Max 25 pts)
            is_high_cricket, c_mult, c_triggers = self.cricket_priority_engine.evaluate_cricket_priority(
                title, summary, category
            )
            importance_score = 15
            if is_high_cricket:
                importance_score = min(25, int(round(15 * c_mult)))

            # 5. Category Priority Score (Max 20 pts)
            # Enforce 75% Cricket / 25% Tech ratio over rolling 30 window
            category_score = 15
            if category == "cricket":
                if balance.priority_boost_active or is_high_cricket:
                    category_score = 20
                elif balance.should_prefer_tech:
                    category_score = 10
            else:  # Technology / non-cricket
                if balance.should_prefer_tech or balance.tech_deficit:
                    category_score = 20  # Boost tech when tech is in deficit to prevent starvation
                elif balance.priority_boost_active:
                    category_score = 10

            # 6. Event Clustering & Cooldown Penalty
            is_event_dup, sim_score, matched_title = self.event_clusterer.check_event_cooldown(
                title, published_history
            )
            cluster_penalty = 50 if is_event_dup else 0

            # Calculate Raw Total Score (0-100)
            base_total = int(round((fresh_score * 0.20) + importance_score + source_score + video_score + category_score))
            total_score = max(0, min(100, base_total - cluster_penalty))

            # Reject non-video assets by dropping total_score if not video available
            if not has_valid_video:
                total_score = 0

            explanation = (
                f"Total Score: {total_score}/100. Video: {video_score}/20, Freshness: {fresh_score}/100, "
                f"Source: {source_score}/15, Importance: {importance_score}/25, Category Priority: {category_score}/20, "
                f"Cluster Penalty: -{cluster_penalty} (Event Dup: {is_event_dup}, Sim: {sim_score:.2f}). "
                f"High Priority Cricket: {is_high_cricket} ({c_triggers})."
            )

            c_score = CandidateScore(
                candidate_id=content_id,
                title=title,
                category=category,
                media_type=media_type,
                source_domain=source_domain,
                published_at=published_at,
                video_available=has_valid_video,
                media_rights_status=rights_status,
                total_score=total_score,
                freshness_score=fresh_score,
                importance_score=importance_score,
                source_reliability_score=source_score,
                video_score=video_score,
                category_priority_score=category_score,
                cluster_penalty=cluster_penalty,
                is_high_priority_cricket=is_high_cricket,
                is_event_duplicate=is_event_dup,
                explanation=explanation,
                raw_item=item,
            )
            scored_candidates.append(c_score)

        # Sort candidates descending by total_score
        ranked = sorted(scored_candidates, key=lambda c: c.total_score, reverse=True)
        top_cand = ranked[0] if ranked and ranked[0].total_score > 0 else None

        logger.info(
            f"ContentIntelligence evaluated {len(raw_candidates)} candidates. "
            f"Top candidate: '{top_cand.title if top_cand else 'None'}' (Score: {top_cand.total_score if top_cand else 0})"
        )

        return {
            "balance_metrics": balance.to_dict() if hasattr(balance, "to_dict") else vars(balance),
            "ranked_candidates": [c.to_dict() for c in ranked],
            "top_candidate": top_cand.to_dict() if top_cand else None,
            "status": "RANKED" if top_cand else "NO_VALID_VIDEO_CANDIDATES",
        }
