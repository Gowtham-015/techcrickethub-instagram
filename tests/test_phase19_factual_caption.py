import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from config import Config
from instagram_automation_engine import InstagramAutomationEngine
from instagram_factual_caption_engine import (
    FactualityVerifier,
    InstagramFactualCaptionEngine,
)


class TestPhase19FactualCaption(unittest.TestCase):
    """Comprehensive test suite for Phase 19 Factual Caption, SEO & Hashtag Engine."""

    def setUp(self):
        self.config = Config.load_from_env(validate=False)
        self.config.dry_run = True
        self.engine = InstagramFactualCaptionEngine()
        self.verifier = FactualityVerifier()

    def test_hallucinated_facts_prevention(self):
        """Verify FactualityVerifier detects hallucinated scores, stats, and quotes."""
        source_text = "India won the T20 match against Australia by 5 wickets in Sydney."

        # Valid caption derived from source
        valid_caption = "🏆 India Won T20 Match Against Australia by 5 Wickets in Sydney."
        is_factual, reasons = self.verifier.verify_factuality(valid_caption, source_text)
        self.assertTrue(is_factual)
        self.assertEqual(len(reasons), 0)

        # Hallucinated score not in source (e.g. 245/4)
        hallucinated_caption = "🏆 India scored 245/4 to win against Australia by 500 runs."
        is_factual_h, reasons_h = self.verifier.verify_factuality(hallucinated_caption, source_text)
        self.assertFalse(is_factual_h)
        self.assertTrue(any("Hallucinated score" in r or "Hallucinated numeric" in r for r in reasons_h))

    def test_missing_source_facts_handling(self):
        """Verify engine generates safe factual caption when summary is minimal without inventing extra facts."""
        res = self.engine.generate_factual_caption(
            title="Tech Firm Announces New Processor",
            summary="",
            category="technology",
            source_domain="techcrunch.com",
        )
        self.assertTrue(res.is_valid)
        self.assertIn("Tech Firm Announces New Processor", res.caption)
        self.assertFalse(res.has_hallucinations)
        self.assertIn("#TechNews", res.caption)

    def test_structured_caption_format(self):
        """Verify 5-part structured caption (Hook, Body, Key Detail, CTA, Hashtags)."""
        res = self.engine.generate_factual_caption(
            title="India Win T20 World Cup Final",
            summary="India defeated South Africa by 7 runs in a historic T20 World Cup final. The team defended the target in a dramatic final over.",
            category="cricket",
            source_domain="espncricinfo.com",
        )
        self.assertTrue(res.is_valid)

        caption = res.caption
        # Hook check
        self.assertIn("🏆 India Win T20 World Cup Final", caption)
        # Key Detail check
        self.assertIn("📌 Key Takeaway:", caption)
        # CTA check
        self.assertIn("Comment below", caption)
        # Hashtags check
        self.assertIn("#TechCricketHub", caption)
        self.assertIn("#Cricket", caption)

    def test_duplicate_caption_detection(self):
        """Verify duplicate or similar caption (>0.55 similarity) against published history is flagged."""
        history = [
            {
                "caption": "🏆 India Win T20 World Cup Final Against South Africa. Defeated South Africa by 7 runs in a historic final.",
            }
        ]

        # Duplicate caption
        res_dup = self.engine.generate_factual_caption(
            title="India Win T20 World Cup Final Against South Africa",
            summary="Defeated South Africa by 7 runs in a historic final.",
            category="cricket",
            published_history=history,
        )
        self.assertTrue(res_dup.is_duplicate)
        self.assertFalse(res_dup.is_valid)

    def test_cricket_vs_tech_hashtags(self):
        """Verify category-specific hashtags for Cricket vs Technology."""
        res_cricket = self.engine.generate_factual_caption(
            title="Cricket Tournament Highlights",
            summary="Highlights of the recent T20 cricket match.",
            category="cricket",
        )
        self.assertIn("#Cricket", res_cricket.hashtags)
        self.assertIn("#CricketNews", res_cricket.hashtags)

        res_tech = self.engine.generate_factual_caption(
            title="Artificial Intelligence Breakthrough",
            summary="New AI model benchmarked today.",
            category="technology",
        )
        self.assertIn("#TechNews", res_tech.hashtags)
        self.assertIn("#AI", res_tech.hashtags)

    def test_clickbait_prevention(self):
        """Verify clickbait phrases are flagged."""
        is_factual, reasons = self.verifier.verify_factuality(
            "You won't believe what happened in this match!",
            "India won the match today."
        )
        self.assertFalse(is_factual)
        self.assertTrue(any("Clickbait" in r for r in reasons))

    def test_end_to_end_prepare_media_stores_factual_caption(self):
        """Verify InstagramAutomationEngine prepare_media generates and stores structured caption."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = Config.load_from_env(validate=False)
            config.dry_run = True
            config.reel_discovery_enabled = True
            auto_engine = InstagramAutomationEngine(config=config, data_dir=tmp_dir)
            auto_engine.news_source = None

            cands = [
                {
                    "content_id": "cand-caption-test",
                    "title": "India Win T20 World Cup Final Historic Victory",
                    "summary": "India defeated South Africa in a thrilling final match.",
                    "category": "cricket",
                    "media_type": "REEL",
                    "video_url": "https://example.com/valid.mp4",
                    "media_rights_status": "OWNED",
                    "rights_evidence": "PROPRIETARY_OWNERSHIP",
                    "commercial_use_allowed": True,
                    "source_domain": "espncricinfo.com",
                }
            ]

            from instagram_media_metadata import MediaAsset
            mock_asset = MediaAsset.from_url("https://example.com/valid.mp4", media_type="REEL", status_code=200)

            with patch.object(auto_engine.source, "get_content_items", return_value=cands):
                with patch.object(auto_engine.acquirer, "acquire_media", return_value=mock_asset):
                    res = auto_engine.prepare_media()
                    self.assertTrue(res.get("prepared"))

                    prepared_file = os.path.join(tmp_dir, "prepared_media.json")
                    self.assertTrue(os.path.exists(prepared_file))
                    with open(prepared_file, "r", encoding="utf-8") as f:
                        prep_data = json.load(f)

                    self.assertIn("🏆 India Win T20 World Cup Final", prep_data.get("caption", ""))
                    self.assertIn("📌 Key Takeaway:", prep_data.get("caption", ""))


if __name__ == "__main__":
    unittest.main()
