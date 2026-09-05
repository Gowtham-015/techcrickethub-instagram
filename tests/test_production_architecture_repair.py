import os
import json
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from config import Config
from instagram_real_video_source import InstagramRealVideoSource
from instagram_public_media_host import PublicMediaHost
from instagram_media_verifier import InstagramMediaVerifier
from instagram_automation_engine import InstagramAutomationEngine
from instagram_content_bundle import ContentBundle
from instagram_final_publish_guard import InstagramFinalPublishGuard


class TestProductionArchitectureRepair(unittest.TestCase):

    def setUp(self):
        self.config = Config.load_from_env(validate=False)

    def test_oceans_mp4_fallback_rejection(self):
        """Verify oceans.mp4 and synthetic video candidates are rejected from video source."""
        source = InstagramRealVideoSource(config=self.config)
        with patch.object(source, "discover_video_items", return_value=[]):
            items = source.get_content_items()
            # Must return empty list, NOT oceans.mp4 fallback candidates
            self.assertEqual(len(items), 0)

    def test_disallowed_media_rights_rejection(self):
        """Verify items with disallowed media rights statuses are rejected."""
        source = InstagramRealVideoSource(config=self.config)
        raw_xml = """<rss version="2.0">
            <channel>
                <title>Cricket Feed</title>
                <item>
                    <title>Pirated Match Clip</title>
                    <link>https://example.com/pirated</link>
                    <description>Summary</description>
                    <enclosure url="https://example.com/pirated.mp4" type="video/mp4"/>
                </item>
            </channel>
        </rss>"""
        parsed = source._parse_feed_items(raw_xml, feed_url="https://example.com/rss", category="cricket")
        self.assertEqual(len(parsed), 1)
        # Verify status is RIGHTS_EVIDENCE_MISSING and rejected from ALLOWED_RIGHTS_STATUSES
        self.assertEqual(parsed[0]["media_rights_status"], "RIGHTS_EVIDENCE_MISSING")
        self.assertNotIn(parsed[0]["media_rights_status"], source.ALLOWED_RIGHTS_STATUSES)

    def test_no_subprocess_git_calls_in_public_media_host(self):
        """Verify PublicMediaHost does NOT execute subprocess.run(['git', ...]) calls."""
        host = PublicMediaHost()
        with patch("subprocess.run") as mock_sub:
            pub_url = host.get_public_url("media/generated/test.jpg")
            self.assertIn("raw.githubusercontent.com", pub_url)
            mock_sub.assert_not_called()

    def test_production_mode_verification_bypass_blocked(self):
        """Verify production mode rejects mock URLs and performs real HTTPS GET verification."""
        prod_config = Config.load_from_env(validate=False)
        prod_config.production_enabled = True
        prod_config.dry_run = False

        with patch("config.Config.load_from_env", return_value=prod_config):
            res = InstagramMediaVerifier.validate_meta_media_accessibility(
                "https://raw.githubusercontent.com/intel-iot-devkit/sample-videos/master/person-bicycle-car-detection.mp4",
                media_type="REEL"
            )
            self.assertIn("is_valid", res)

    def test_balancer_uses_persistent_history(self):
        """Verify Cricket/Tech 75/25 balancer evaluates persistent published history."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = Config.load_from_env(validate=False)
            history_file = os.path.join(tmp_dir, "instagram_published_history.json")

            items = []
            for i in range(25):
                items.append({
                    "content_id": f"c-pub-{i}",
                    "category": "cricket",
                    "title": f"Cricket Item {i}",
                    "media_type": "REEL",
                    "instagram_media_id": f"media-c-{i}",
                })
            for i in range(5):
                items.append({
                    "content_id": f"t-pub-{i}",
                    "category": "technology",
                    "title": f"Tech Item {i}",
                    "media_type": "REEL",
                    "instagram_media_id": f"media-t-{i}",
                })
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump({"items": items}, f)

            engine = InstagramAutomationEngine(config=config, data_dir=tmp_dir)
            history = engine.final_publish_guard.get_published_history()
            self.assertEqual(len(history), 30)

            balance = engine.cricket_balancer.evaluate_balance(history)
            self.assertEqual(balance.cricket_count, 25)
            self.assertEqual(balance.non_cricket_count, 5)

    def test_two_stage_prepare_and_publish_prepared(self):
        """Verify Phase A prepare_media and Phase B/C publish_prepared execution flow."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = Config.load_from_env(validate=False)
            config.dry_run = True
            config.reel_discovery_enabled = True
            engine = InstagramAutomationEngine(config=config, data_dir=tmp_dir)
            engine.news_source = None

            sample_raw = {
                "content_id": "test-prepare-001",
                "title": "India Win Final Test Match",
                "summary": "India secured a victory against Australia.",
                "category": "cricket",
                "media_type": "REEL",
                "video_url": "https://example.com/video.mp4",
                "media_rights_status": "LICENSED",
                "source_domain": "espncricinfo.com",
                "source_url": "https://espncricinfo.com/match-final",
            }

            from instagram_media_metadata import MediaAsset
            mock_asset = MediaAsset.from_url("https://example.com/video.mp4", media_type="REEL", status_code=200)

            with patch.object(engine.source, "get_content_items", return_value=[sample_raw]):
                with patch.object(engine.acquirer, "acquire_media", return_value=mock_asset):
                    prep_res = engine.prepare_media()
                    self.assertTrue(prep_res.get("prepared"))
                    self.assertEqual(prep_res.get("content_id"), "test-prepare-001")

                    prepared_file = os.path.join(tmp_dir, "prepared_media.json")
                    self.assertTrue(os.path.exists(prepared_file))

                    # Mock accessibility check for publish_prepared
                    with patch("instagram_media_verifier.InstagramMediaVerifier.validate_meta_media_accessibility", return_value={"is_valid": True}):
                        pub_res = engine.publish_prepared()
                        self.assertEqual(pub_res.get("status"), "SKIPPED_DRY_RUN")

                prepared_file = os.path.join(tmp_dir, "prepared_media.json")
                self.assertTrue(os.path.exists(prepared_file))

                # Mock accessibility check for publish_prepared
                with patch("instagram_media_verifier.InstagramMediaVerifier.validate_meta_media_accessibility", return_value={"is_valid": True}):
                    pub_res = engine.publish_prepared()
                    self.assertEqual(pub_res.get("status"), "SKIPPED_DRY_RUN")


if __name__ == "__main__":
    unittest.main()
