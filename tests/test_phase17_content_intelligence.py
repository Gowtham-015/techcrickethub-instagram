import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from config import Config
from instagram_automation_engine import InstagramAutomationEngine
from instagram_content_intelligence import (
    CandidateScore,
    ContentIntelligenceEngine,
    CricketPriorityEngine,
    EventClusterer,
    FreshnessScorer,
    SourceReliabilityScorer,
)


class TestPhase17ContentIntelligence(unittest.TestCase):
    """Comprehensive test suite for Phase 17 Content Intelligence & Cricket Priority Engine."""

    def setUp(self):
        self.config = Config.load_from_env(validate=False)
        self.config.dry_run = True
        self.config.production_enabled = False
        self.engine = ContentIntelligenceEngine(config=self.config)

    def test_rolling_30_window_counters_and_ratio(self):
        """Verify rolling 30 window category counters calculate 75% Cricket / 25% Tech targets."""
        # 30 items: 25 cricket, 5 tech (tech is starved < 7 items)
        published_history = [{"category": "cricket", "title": f"Cricket {i}"} for i in range(25)]
        published_history.extend([{"category": "technology", "title": f"Tech {i}"} for i in range(5)])

        raw_candidates = [
            {
                "content_id": "cand-cricket-1",
                "title": "India Win World Cup Final",
                "summary": "India won the cricket match.",
                "category": "cricket",
                "media_type": "REEL",
                "video_url": "https://example.com/video1.mp4",
                "media_rights_status": "OWNED",
                "source_domain": "espncricinfo.com",
            },
            {
                "content_id": "cand-tech-1",
                "title": "New AI Quantum Computer Breakthrough Announced",
                "summary": "Scientists built a new quantum processor.",
                "category": "technology",
                "media_type": "REEL",
                "video_url": "https://example.com/video2.mp4",
                "media_rights_status": "OWNED",
                "source_domain": "techcrunch.com",
            },
        ]

        report = self.engine.evaluate_and_rank_candidates(raw_candidates, published_history)
        metrics = report.get("balance_metrics", {})
        self.assertEqual(metrics.get("total_items"), 30)
        self.assertEqual(metrics.get("cricket_count"), 25)
        self.assertEqual(metrics.get("non_cricket_count"), 5)
        self.assertTrue(metrics.get("tech_deficit"))
        self.assertTrue(metrics.get("should_prefer_tech"))

    def test_technology_minimum_quota_guard(self):
        """Verify technology minimum quota guard boosts tech priority when tech is starved."""
        # History: 28 cricket, 2 tech (severe tech starvation)
        history = [{"category": "cricket", "title": f"Cricket {i}"} for i in range(28)]
        history.extend([{"category": "technology", "title": f"Tech {i}"} for i in range(2)])

        raw_candidates = [
            {
                "content_id": "cand-c1",
                "title": "Standard Cricket Match Result",
                "summary": "County match concluded today.",
                "category": "cricket",
                "media_type": "REEL",
                "video_url": "https://example.com/cricket.mp4",
                "media_rights_status": "OWNED",
                "source_domain": "espncricinfo.com",
            },
            {
                "content_id": "cand-t1",
                "title": "New Smartphone Launch Tech Breakthrough",
                "summary": "Latest flagship smartphone revealed with fast chip.",
                "category": "technology",
                "media_type": "REEL",
                "video_url": "https://example.com/tech.mp4",
                "media_rights_status": "OWNED",
                "source_domain": "techcrunch.com",
            },
        ]

        report = self.engine.evaluate_and_rank_candidates(raw_candidates, history)
        ranked = report.get("ranked_candidates", [])
        self.assertTrue(len(ranked) >= 2)

        # Tech item should receive boosted category_priority_score (20/20) due to tech deficit
        tech_score = next(c for c in ranked if c["category"] == "technology")
        self.assertEqual(tech_score["category_priority_score"], 20)

    def test_cricket_priority_triggers(self):
        """Verify cricket priority engine detects live match, World Cup, finals, and player announcements."""
        cricket_engine = CricketPriorityEngine()

        # Major tournament + final
        is_hp, mult, triggers = cricket_engine.evaluate_cricket_priority(
            title="India Win T20 World Cup Final Thriller",
            summary="Historic victory for India in the World Cup final match.",
            category="cricket",
        )
        self.assertTrue(is_hp)
        self.assertTrue(mult >= 1.5)
        self.assertTrue(any("WORLD CUP" in t or "FINAL" in t for t in triggers))

        # Player retirement announcement
        is_hp2, mult2, triggers2 = cricket_engine.evaluate_cricket_priority(
            title="Legendary Player Announces Retirement From All Formats",
            summary="BCCI confirms captain steps down after historic career.",
            category="cricket",
        )
        self.assertTrue(is_hp2)
        self.assertTrue(any("RETIRE" in t or "ANNOUNCEMENT" in t for t in triggers2))

    def test_event_clustering_cooldown(self):
        """Verify EventClusterer penalizes articles matching recently published articles on the same event."""
        clusterer = EventClusterer()
        history = [
            {
                "title": "India Win T20 World Cup Final Against South Africa in Barbados",
                "published_at": "2026-09-06T10:00:00Z",
            }
        ]

        # Candidate covering the EXACT SAME event
        cand_title = "India Win T20 World Cup Final Against South Africa in Barbados Historic Victory"
        is_dup, sim, prev = clusterer.check_event_cooldown(cand_title, history)

        self.assertTrue(is_dup)
        self.assertTrue(sim >= 0.45)

    def test_freshness_time_decay(self):
        """Verify FreshnessScorer decays score based on article age."""
        scorer = FreshnessScorer()

        score_fresh = scorer.calculate_freshness_score("2026-09-06T16:00:00Z")
        self.assertTrue(score_fresh >= 85)

        score_old = scorer.calculate_freshness_score("2026-09-01T10:00:00Z")
        self.assertTrue(score_old <= 35)

    def test_source_reliability_scoring(self):
        """Verify SourceReliabilityScorer rates tier-1 domains higher."""
        scorer = SourceReliabilityScorer()

        self.assertEqual(scorer.calculate_source_score("espncricinfo.com"), 100)
        self.assertEqual(scorer.calculate_source_score("bbc.com"), 100)
        self.assertEqual(scorer.calculate_source_score("techcrunch.com"), 85)
        self.assertEqual(scorer.calculate_source_score("unknown-blog.xyz"), 70)

    def test_image_only_candidate_rejection(self):
        """Verify candidate without valid video receives 0 total score under 100% Reel target mode."""
        raw_candidates = [
            {
                "content_id": "cand-img-1",
                "title": "Image Only News Article",
                "summary": "This article has no video.",
                "category": "cricket",
                "media_type": "IMAGE",
                "image_url": "https://example.com/image.jpg",
                "media_rights_status": "OWNED",
            }
        ]

        report = self.engine.evaluate_and_rank_candidates(raw_candidates, [])
        ranked = report.get("ranked_candidates", [])
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0]["total_score"], 0)
        self.assertFalse(ranked[0]["video_available"])
        self.assertEqual(report["status"], "NO_VALID_VIDEO_CANDIDATES")

    def test_end_to_end_engine_candidate_ranking(self):
        """Verify InstagramAutomationEngine prepare_media uses ContentIntelligenceEngine to rank candidates."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = Config.load_from_env(validate=False)
            config.dry_run = True
            config.reel_discovery_enabled = True
            auto_engine = InstagramAutomationEngine(config=config, data_dir=tmp_dir)
            auto_engine.news_source = None

            cands = [
                {
                    "content_id": "cand-low",
                    "title": "Random Low Priority Post",
                    "summary": "Minor update on local club.",
                    "category": "cricket",
                    "media_type": "REEL",
                    "video_url": "https://example.com/low.mp4",
                    "media_rights_status": "OWNED",
                    "source_domain": "unknown.com",
                },
                {
                    "content_id": "cand-high",
                    "title": "India Win T20 World Cup Final Historic Victory",
                    "summary": "Unbelievable victory for India in the final.",
                    "category": "cricket",
                    "media_type": "REEL",
                    "video_url": "https://example.com/high.mp4",
                    "media_rights_status": "OWNED",
                    "source_domain": "espncricinfo.com",
                },
            ]

            from instagram_media_metadata import MediaAsset
            mock_asset = MediaAsset.from_url("https://example.com/high.mp4", media_type="REEL", status_code=200)

            with patch.object(auto_engine.source, "get_content_items", return_value=cands):
                with patch.object(auto_engine.acquirer, "acquire_media", return_value=mock_asset):
                    res = auto_engine.prepare_media()

                    self.assertTrue(res.get("prepared"))
                    # Must select high-priority candidate 'cand-high' over 'cand-low'
                    self.assertEqual(res.get("content_id"), "cand-high")


if __name__ == "__main__":
    unittest.main()
