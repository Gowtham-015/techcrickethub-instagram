import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from instagram_content_analytics import InstagramContentAnalytics
from instagram_content_bundle import ContentBundle
from main import run_content_analytics


class TestPhase22InstagramAnalytics(unittest.TestCase):
    """Unit test suite for Phase 22 Instagram Content Analytics and Meta Graph API Insights Sync."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.analytics_file = os.path.join(self.tmp_dir.name, "instagram_content_analytics.json")
        self.engine = InstagramContentAnalytics(analytics_file=self.analytics_file)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_record_published_item_persistence(self):
        """Verify record_published_item stores real published Reel entries cleanly."""
        bundle = ContentBundle(
            content_id="analytics-101",
            category="cricket",
            title="India Wins T20 Thriller Match",
            summary="Spectacular bowling display in the final over.",
            source_url="https://cricinfo.com/match101",
            source_domain="cricinfo.com",
            published_at="2026-09-10T12:00:00Z",
            media_url="https://raw.githubusercontent.com/test.mp4",
            media_type="REEL",
        )

        entry = self.engine.record_published_item(bundle=bundle, media_id="ig_media_101", permalink="https://instagram.com/reel/101")
        self.assertEqual(entry["media_id"], "ig_media_101")
        self.assertEqual(entry["category"], "cricket")
        self.assertEqual(entry["topic"], "IPL & T20 Cricket")
        self.assertEqual(entry["reach"], 0)
        self.assertEqual(entry["engagement_rate"], 0.0)

        summary = self.engine.get_analytics_summary()
        self.assertEqual(summary["total_published"], 1)
        self.assertEqual(summary["reel_count"], 1)
        self.assertEqual(summary["cricket_count"], 1)

    def test_sync_meta_insights_no_fake_metrics(self):
        """Verify sync_meta_insights does not generate fake data when API token is missing or call fails."""
        bundle = ContentBundle(
            content_id="analytics-102",
            category="technology",
            title="AI Chip Architecture Breakthrough",
            summary="New silicon design promises 3x efficiency.",
            source_url="https://techcrunch.com/ai-chip",
            source_domain="techcrunch.com",
            published_at="2026-09-10T14:00:00Z",
            media_url="https://raw.githubusercontent.com/test_tech.mp4",
            media_type="REEL",
        )
        self.engine.record_published_item(bundle=bundle, media_id="ig_media_102")

        # Sync without token
        res = self.engine.sync_meta_insights(access_token=None)
        self.assertEqual(res["synced_count"], 0)

        summary = self.engine.get_analytics_summary()
        self.assertEqual(summary["total_likes"], 0)
        self.assertEqual(summary["total_views"], 0)
        self.assertEqual(summary["average_engagement_rate"], 0.0)

    @patch("urllib.request.urlopen")
    def test_sync_meta_insights_real_api_mock(self, mock_urlopen):
        """Verify sync_meta_insights parses real Meta Graph API response data and calculates engagement rate."""
        bundle = ContentBundle(
            content_id="analytics-103",
            category="cricket",
            title="IPL 2026 Opening Match Highlights",
            summary="Record-breaking crowd witnesses thrilling chase.",
            source_url="https://cricinfo.com/ipl-103",
            source_domain="cricinfo.com",
            published_at="2026-09-10T16:00:00Z",
            media_url="https://raw.githubusercontent.com/test_ipl.mp4",
            media_type="REEL",
        )
        self.engine.record_published_item(bundle=bundle, media_id="179001122334455")

        # Mock fields response
        mock_fields_resp = MagicMock()
        mock_fields_resp.getcode.return_value = 200
        mock_fields_resp.read.return_value = json.dumps({
            "like_count": 250,
            "comments_count": 40,
            "permalink": "https://instagram.com/reel/ipl103",
        }).encode("utf-8")

        # Mock insights response
        mock_insights_resp = MagicMock()
        mock_insights_resp.getcode.return_value = 200
        mock_insights_resp.read.return_value = json.dumps({
            "data": [
                {"name": "reach", "values": [{"value": 5000}]},
                {"name": "plays", "values": [{"value": 7500}]},
                {"name": "saved", "values": [{"value": 60}]},
                {"name": "shares", "values": [{"value": 150}]},
            ]
        }).encode("utf-8")

        mock_urlopen.side_effect = [
            MagicMock(__enter__=MagicMock(return_value=mock_fields_resp)),
            MagicMock(__enter__=MagicMock(return_value=mock_insights_resp)),
        ]

        res = self.engine.sync_meta_insights(access_token="test_token_123")
        self.assertEqual(res["synced_count"], 1)

        summary = self.engine.get_analytics_summary()
        self.assertEqual(summary["total_likes"], 250)
        self.assertEqual(summary["total_comments"], 40)
        self.assertEqual(summary["total_shares"], 150)
        self.assertEqual(summary["total_saves"], 60)
        self.assertEqual(summary["total_views"], 7500)
        # engagement_rate = (250 + 40 + 150 + 60) / 7500 * 100 = 500 / 7500 * 100 = 6.67%
        self.assertEqual(summary["average_engagement_rate"], 6.67)

    def test_run_content_analytics_runner(self):
        """Verify main.py --content-analytics command runner executes cleanly."""
        res = run_content_analytics(sync_meta=False)
        self.assertTrue(res)


if __name__ == "__main__":
    unittest.main()
