import unittest
from unittest.mock import MagicMock, patch

from instagram_caption_generator import InstagramCaptionGenerator
from instagram_category_intelligence import InstagramCategoryIntelligence
from instagram_cricket_match_intelligence import InstagramCricketMatchIntelligence, MatchIntelligenceSummary
from instagram_real_video_source import InstagramRealVideoSource


class TestAutonomousAgentExpansion(unittest.TestCase):
    """Test suite verifying multi-category expansion, Cricket Live/Off-Day intelligence, and caption formatting."""

    def setUp(self):
        self.source = InstagramRealVideoSource()
        self.cat_intel = InstagramCategoryIntelligence()
        self.match_intel = InstagramCricketMatchIntelligence()
        self.caption_gen = InstagramCaptionGenerator()

    def test_multi_category_discovery(self):
        """Verify video items can be discovered across all expanded categories."""
        sample_rss = """<rss version="2.0">
            <channel>
                <title>Feed Title</title>
                <item>
                    <title>Category News Reel</title>
                    <link>https://example.com/story</link>
                    <description>Story summary</description>
                    <enclosure url="https://example.com/video.mp4" type="video/mp4"/>
                    <creativeCommons>https://creativecommons.org/licenses/by/4.0/</creativeCommons>
                </item>
            </channel>
        </rss>"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = sample_rss

        categories = ["cricket", "technology", "geopolitics", "democracy", "entertainment"]
        with patch("requests.get", return_value=mock_resp):
            for cat in categories:
                items = self.source.discover_video_items(category=cat, limit=1)
                self.assertGreater(len(items), 0, f"No candidates found for category {cat}")
                first = items[0]
                self.assertEqual(first["category"], cat)
                self.assertEqual(first["media_type"], "REEL")
                self.assertIn(first["media_rights_status"], self.source.ALLOWED_RIGHTS_STATUSES)

    def test_category_keyword_detection(self):
        """Verify category intelligence detects geopolitics and democracy keywords."""
        cat_geo, conf_geo = self.cat_intel.detect_category("Global Summit Update", "Diplomacy and international relations discussed at G20")
        self.assertEqual(cat_geo, "geopolitics")
        self.assertGreater(conf_geo, 0.0)

        cat_dem, conf_dem = self.cat_intel.detect_category("Parliament Election Update", "Supreme court rules on election governance bill")
        self.assertEqual(cat_dem, "democracy")
        self.assertGreater(conf_dem, 0.0)

    def test_cricket_match_intelligence_states(self):
        """Verify Cricket match intelligence distinguishes live match day from off-day."""
        # Case 1: Live match
        mock_live_match = MagicMock(status="LIVE")
        summary_live = self.match_intel.analyze_matches(matches=[mock_live_match])
        self.assertEqual(summary_live.state, "LIVE_MATCH")
        self.assertTrue(summary_live.is_match_day)

        # Case 2: Off-day (no matches)
        summary_off = self.match_intel.analyze_matches(matches=[])
        self.assertEqual(summary_off.state, "NO_MATCH")
        self.assertFalse(summary_off.is_match_day)

    def test_professional_caption_generation_expanded(self):
        """Verify professional captions are formatted cleanly with emojis, hashtags, and call-to-actions."""
        caption_geo = self.caption_gen.generate_caption(
            title="Global Summit Agreement Reached",
            summary="World leaders align on international trade and climate goals.",
            category="geopolitics",
            source="g20.org",
        )
        self.assertIn("🌐 Global Summit Agreement Reached", caption_geo)
        self.assertIn("#Geopolitics", caption_geo)
        self.assertIn("💬 What do you think? Comment below!", caption_geo)

        caption_dem = self.caption_gen.generate_caption(
            title="Landmark Electoral Reform Passed",
            summary="Parliament approves transparent voting standards for upcoming national elections.",
            category="democracy",
            source="governance.gov",
        )
        self.assertIn("🏛️ Landmark Electoral Reform Passed", caption_dem)
        self.assertIn("#Democracy", caption_dem)


if __name__ == "__main__":
    unittest.main()
