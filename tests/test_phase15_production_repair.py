import os
import json
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from config import Config
from instagram_real_video_source import InstagramRealVideoSource
from instagram_media_verifier import InstagramMediaVerifier
from instagram_automation_engine import InstagramAutomationEngine
from instagram_content_bundle import ContentBundle
from instagram_final_publish_guard import InstagramFinalPublishGuard


class TestPhase15ProductionRepair(unittest.TestCase):

    def setUp(self):
        self.config = Config.load_from_env(validate=False)

    def test_real_video_source_rights_verification(self):
        """Test 1 & 2: InstagramRealVideoSource accepts allowed rights and rejects unverified rights."""
        source = InstagramRealVideoSource(config=self.config)
        self.assertIn("OWNED", source.ALLOWED_RIGHTS_STATUSES)
        self.assertIn("LICENSED", source.ALLOWED_RIGHTS_STATUSES)
        self.assertIn("AUTHORIZED", source.ALLOWED_RIGHTS_STATUSES)
        self.assertIn("PUBLIC_DOMAIN", source.ALLOWED_RIGHTS_STATUSES)
        self.assertIn("CC_LICENSE_ALLOWED", source.ALLOWED_RIGHTS_STATUSES)
        self.assertNotIn("RIGHTS_NOT_VERIFIED", source.ALLOWED_RIGHTS_STATUSES)
        self.assertNotIn("UNKNOWN", source.ALLOWED_RIGHTS_STATUSES)

    @patch("requests.get")
    def test_source_url_and_video_url_separation(self, mock_get):
        """Test 3: source_url (article) and video_url (MP4 asset) are strictly separated."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '<rss><channel><item><title>Test</title><link>https://bcci.tv/test</link><enclosure url="https://files.catbox.moe/test.mp4" type="video/mp4"/></item></channel></rss>'
        mock_get.return_value = mock_resp

        source = InstagramRealVideoSource(config=self.config)
        items = source.discover_video_items(category="cricket", limit=2)
        self.assertTrue(len(items) > 0)
        item = items[0]
        self.assertIn("source_url", item)
        self.assertIn("video_url", item)
        self.assertNotEqual(item["source_url"], item["video_url"])


    @patch("urllib.request.urlopen")
    def test_wait_for_public_media_retries(self, mock_urlopen):
        """Test 5: wait_for_public_media executes bounded retries before reporting ready or failed."""
        mock_resp = MagicMock()
        mock_resp.getcode.return_value = 200
        mock_resp.headers = {"Content-Type": "video/mp4", "Content-Length": "50000"}
        mock_resp.read.side_effect = [b"\x00\x00\x00\x18ftypisom" + b"\x00" * 2000, b"\x00" * 48000]
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = InstagramMediaVerifier.wait_for_public_media("https://raw.githubusercontent.com/test.mp4", media_type="REEL", max_attempts=2, delay_seconds=0.01)
        self.assertTrue(res["is_valid"])

    def test_last_production_run_and_proof_persistence(self):
        """Test 8: Engine persists last_production_run.json and production_proof.json post-cycle."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = Config.load_from_env(validate=False)
            config.dry_run = True
            engine = InstagramAutomationEngine(config=config, data_dir=tmp_dir)

            with patch.object(engine.source, "get_content_items", return_value=[]):
                cycle_res = engine.run_cycle()

            last_run_file = os.path.join(tmp_dir, "last_production_run.json")
            proof_file = os.path.join(tmp_dir, "production_proof.json")

            self.assertTrue(os.path.exists(last_run_file))
            self.assertTrue(os.path.exists(proof_file))

            with open(last_run_file, "r", encoding="utf-8") as f:
                last_run_data = json.load(f)
                self.assertIn("run_id", last_run_data)
                self.assertIn("status", last_run_data)

            with open(proof_file, "r", encoding="utf-8") as f:
                proof_data = json.load(f)
                self.assertIn("github_actions_run_id", proof_data)
                self.assertIn("status", proof_data)


if __name__ == "__main__":
    unittest.main()
