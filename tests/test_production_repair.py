import os
import json
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from config import Config
from instagram_media_verifier import InstagramMediaVerifier, MediaVerificationResult
from instagram_publisher import InstagramImagePublisher
from instagram_reel_publisher import InstagramReelPublisher, PublishResult
from instagram_final_publish_guard import InstagramFinalPublishGuard
from instagram_publish_lock import InstagramPublishLock
from instagram_automation_engine import InstagramAutomationEngine
from instagram_content_bundle import ContentBundle
from instagram_reel_generator import InstagramReelGenerator


class TestProductionRepair(unittest.TestCase):

    def setUp(self):
        self.config = Config.load_from_env(validate=False)

    @patch("urllib.request.urlopen")
    def test_github_raw_http_404_fails(self, mock_urlopen):
        """Test 1 & 2: HTTP 404 from GitHub Raw fails with MEDIA_PUBLICATION_BLOCKED."""
        mock_resp = MagicMock()
        mock_resp.getcode.return_value = 404
        mock_resp.headers = {}
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError("https://raw.githubusercontent.com/test_probe/404.mp4", 404, "Not Found", {}, None)

        res = InstagramMediaVerifier.validate_meta_media_accessibility("https://raw.githubusercontent.com/test_probe/404.mp4", media_type="REEL")
        self.assertFalse(res["is_valid"])
        self.assertEqual(res["error_code"], "MEDIA_PUBLICATION_BLOCKED")

    @patch("urllib.request.urlopen")
    def test_github_raw_html_response_fails(self, mock_urlopen):
        """Test 3: HTML webpage disguise returned by public URL fails verification."""
        mock_resp = MagicMock()
        mock_resp.getcode.return_value = 200
        mock_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
        mock_resp.read.return_value = b"<!DOCTYPE html><html><head><title>404 Not Found</title></head></html>"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = InstagramMediaVerifier.validate_meta_media_accessibility("https://raw.githubusercontent.com/test_probe/html.mp4", media_type="REEL")
        self.assertFalse(res["is_valid"])
        self.assertEqual(res["error_code"], "MEDIA_PUBLICATION_BLOCKED")
        self.assertIn("HTML webpage", res["error"])

    @patch("urllib.request.urlopen")
    def test_public_mp4_validation_success(self, mock_urlopen):
        """Test 4: Real MP4 binary file returns PUBLIC_MEDIA_VALID."""
        mock_resp = MagicMock()
        mock_resp.getcode.return_value = 200
        mock_resp.headers = {"Content-Type": "video/mp4", "Content-Length": "102400"}
        # ftyp header for mp4
        mock_resp.read.side_effect = [b"\x00\x00\x00\x18ftypisom" + b"\x00" * 4000, b"\x00" * 98304]
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = InstagramMediaVerifier.validate_meta_media_accessibility("https://raw.githubusercontent.com/test_probe/valid.mp4", media_type="REEL")
        self.assertTrue(res["is_valid"])
        self.assertEqual(res["status_code"], "PUBLIC_MEDIA_VALID")


    def test_local_vs_public_mp4_distinction(self):
        """Test 5: Local file verification distinguishes LOCAL_MEDIA_VALID from PUBLIC_MEDIA_VALID."""
        verifier = InstagramMediaVerifier()
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        gen_dir = os.path.join(base_dir, "data", "generated_reels")
        os.makedirs(gen_dir, exist_ok=True)
        tmp_reel = os.path.join(gen_dir, "reel_real-unittest101.mp4")

        with open(tmp_reel, "wb") as f:
            f.write(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 1000)

        try:
            raw_url = "https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/data/generated_reels/reel_real-unittest101.mp4"
            unique_source = f"https://example.com/unique-story-{os.urandom(4).hex()}"
            res = verifier.verify_and_deduplicate(url=raw_url, media_type="REEL", source_url=unique_source)
            self.assertTrue(res.is_valid)
            self.assertEqual(res.error_code, "LOCAL_MEDIA_VALID")
        finally:
            if os.path.exists(tmp_reel):
                os.remove(tmp_reel)

    @patch("instagram_media_verifier.InstagramMediaVerifier.validate_meta_media_accessibility")
    def test_inaccessible_media_blocks_container_creation(self, mock_access):
        """Test 6: Inaccessible media stops Reel publisher before calling Meta API."""
        mock_access.return_value = {"is_valid": False, "error_code": "MEDIA_PUBLICATION_BLOCKED", "error": "HTTP 404"}
        mock_client = MagicMock()
        publisher = InstagramReelPublisher(client=mock_client)

        res = publisher.publish_reel("https://raw.githubusercontent.com/missing.mp4", "Caption")
        self.assertFalse(res.success)
        self.assertEqual(res.status, "MEDIA_FAILED")
        self.assertIn("MEDIA_PUBLICATION_BLOCKED", res.message)
        # Verify Meta API post was NOT called
        mock_client.post.assert_not_called()

    @patch("instagram_media_verifier.InstagramMediaVerifier.validate_meta_media_accessibility")
    def test_container_finished_then_media_publish_failure(self, mock_access):
        """Test 7 & 8: Container created & FINISHED, but media_publish fails."""
        mock_access.return_value = {"is_valid": True}
        mock_client = MagicMock()
        mock_client.user_id = "12345"
        mock_client.post.side_effect = [
            {"id": "container-999"},  # container creation
            {"error": "Publish failed"},  # media_publish
        ]
        mock_client.get.return_value = {"status_code": "FINISHED"}

        publisher = InstagramReelPublisher(client=mock_client)
        res = publisher.publish_reel("https://raw.githubusercontent.com/valid.mp4", "Caption")
        self.assertFalse(res.success)

    def test_reel_failure_does_not_become_image(self):
        """Test 21: Reel candidate failure is REJECTED and NOT converted to image."""
        raw_item = {
            "content_id": "test-reel-fail",
            "title": "Reel Match News",
            "summary": "Match details",
            "category": "cricket",
            "media_type": "REEL",
            "video_url": None,  # Missing video
            "image_url": "https://example.com/photo.jpg",
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = Config.load_from_env(validate=False)
            config.reel_discovery_enabled = True
            engine = InstagramAutomationEngine(config=config, data_dir=tmp_dir)

            with patch.object(engine.source, "get_content_items", return_value=[raw_item]):
                cycle_res = engine.run_cycle()
                self.assertEqual(cycle_res["published"], 0)
                self.assertEqual(cycle_res["queued"], 0)


    def test_duplicate_prevention_on_story(self):
        """Test 11-15: Duplicate guard rejects identical story/url/title."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            guard = InstagramFinalPublishGuard(config=self.config, data_dir=tmp_dir)
            unique_source = f"https://cricinfo.com/match-unit-{os.urandom(4).hex()}"
            bundle = ContentBundle(
                content_id=f"dup-{os.urandom(4).hex()}",
                category="cricket",
                title="Australia vs England Test Highlight Match",
                summary="Australia score 350 runs in first innings",
                source_url=unique_source,
                source_domain="cricinfo.com",
                published_at="2026-08-27T10:00:00Z",
                media_url="https://raw.githubusercontent.com/user/repo/main/data/generated_reels/reel_match_101.mp4",
                media_type="REEL",
                media_rights_status="LICENSED",
                caption="Australia vs England Test Highlight Match #cricket",
            )

            res1 = guard.verify_and_guard(bundle)
            self.assertTrue(res1.is_valid)

            # Record publication
            guard.record_published_item(bundle, media_id="189999999999")

            # Second attempt must be rejected
            res2 = guard.verify_and_guard(bundle)
            self.assertFalse(res2.is_valid)
            self.assertEqual(res2.error_code, "DUPLICATE_SOURCE")


    def test_stale_lock_recovery(self):
        """Test 27: Stale publish lock is automatically recovered."""
        with tempfile.NamedTemporaryFile(suffix=".lock", delete=False) as f:
            f.write(b"pid=9999,time=1000000000.0")
            lock_path = f.name

        try:
            lock = InstagramPublishLock(lock_file=lock_path, stale_threshold_seconds=1.0)
            # Acquired should succeed by breaking stale lock
            acquired = lock.acquire()
            self.assertTrue(acquired)
            lock.release()
        finally:
            if os.path.exists(lock_path):
                os.remove(lock_path)


if __name__ == "__main__":
    unittest.main()
