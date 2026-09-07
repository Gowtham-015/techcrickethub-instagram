import os
import json
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from config import Config
from instagram_automation_engine import InstagramAutomationEngine
from instagram_factual_caption_engine import InstagramFactualCaptionEngine, CaptionGenerationResult
from instagram_rights_evidence_engine import InstagramRightsEvidenceEngine
from instagram_reel_quality_engine import InstagramReelQualityEngine
from instagram_real_video_verifier import InstagramRealVideoVerifier
from instagram_public_media_host import PublicMediaHost
from instagram_publisher import InstagramImagePublisher
from exceptions import InstagramError


class TestPhase20_1ProductionHardening(unittest.TestCase):
    """Unit tests for Phase 20.1 Final Integration & Production Hardening."""

    def setUp(self):
        self.config = Config.load_from_env(validate=False)
        self.config.dry_run = True
        self.config.production_enabled = True

    def test_reel_only_defaults_and_image_rejection(self):
        """Verify 100% Reel-only configuration defaults and IMAGE candidate rejection."""
        self.assertEqual(self.config.reel_target_percent, 100)
        self.assertEqual(self.config.image_target_percent, 0)
        self.assertFalse(self.config.enable_image_fallback)

        with tempfile.TemporaryDirectory() as tmp_dir:
            engine = InstagramAutomationEngine(config=self.config, data_dir=tmp_dir)
            engine.news_source = None

            image_raw = {
                "content_id": "test-image-001",
                "title": "Test Image Candidate",
                "summary": "This is an image candidate that must be rejected.",
                "category": "cricket",
                "media_type": "IMAGE",
                "image_url": "https://example.com/image.jpg",
                "media_rights_status": "OWNED",
                "rights_status": "OWNED",
                "rights_evidence": "Owned image",
                "license_url": "https://techcrickethub.com/terms",
                "commercial_use_allowed": True,
            }

            with patch.object(engine.source, "get_content_items", return_value=[image_raw]):
                res = engine.prepare_media()
                self.assertFalse(res.get("prepared"))
                self.assertIn(res.get("status"), ("NO_CANDIDATES", "NO_VALID_REEL"))

    def test_factual_caption_fail_closed(self):
        """Verify factual caption failure rejects candidate without title fallback."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            engine = InstagramAutomationEngine(config=self.config, data_dir=tmp_dir)
            engine.news_source = None

            reel_raw = {
                "content_id": "test-caption-fail-001",
                "title": "Test Reel Candidate",
                "summary": "Summary context.",
                "category": "cricket",
                "media_type": "REEL",
                "video_url": "https://example.com/video.mp4",
                "media_rights_status": "OWNED",
                "rights_status": "OWNED",
                "rights_evidence": "Owned reel",
                "license_url": "https://techcrickethub.com/terms",
                "commercial_use_allowed": True,
            }

            failed_cap_res = CaptionGenerationResult(
                is_valid=False,
                caption="",
                hook="",
                body_sentences=[],
                key_detail="",
                cta="",
                hashtags=[],
                has_hallucinations=True,
                is_duplicate=False,
                reasons=["Hallucinated stat detected."],
            )

            from instagram_media_metadata import MediaAsset
            mock_asset = MediaAsset.from_url("https://example.com/video.mp4", media_type="REEL", status_code=200)

            with patch.object(engine.source, "get_content_items", return_value=[reel_raw]):
                with patch.object(engine.acquirer, "acquire_media", return_value=mock_asset):
                    with patch.object(engine.factual_caption_engine, "generate_factual_caption", return_value=failed_cap_res):
                        res = engine.prepare_media()
                        self.assertFalse(res.get("prepared"))
                        self.assertIn(res.get("status"), ("FAILED", "NO_VALID_REEL"))
                        self.assertIn("Factual caption verification failed", res.get("reason"))

    def test_strict_rights_defaults_fail_closed(self):
        """Verify missing commercial_use_allowed permission defaults to False and rejects candidate."""
        engine = InstagramRightsEvidenceEngine()
        item_missing_comm = {
            "content_id": "test-no-comm-001",
            "media_rights_status": "LICENSED",
            "rights_evidence": "Licensed agreement",
            "license_url": "https://example.com/license",
            # "commercial_use_allowed" is omitted
        }
        res = engine.verify_rights_evidence(item_missing_comm)
        self.assertFalse(res.is_valid)
        self.assertFalse(res.commercial_use_allowed)
        self.assertIn("Explicit commercial_use_allowed = True permission is required and missing.", res.reasons)

    def test_strict_production_ffprobe_quality(self):
        """Verify production mode fails closed when ffprobe returns no video stream."""
        quality_engine = InstagramReelQualityEngine()
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"invalid corrupt video content")
            tmp_path = f.name

        try:
            # Production mode (is_mock=False)
            res = quality_engine.validate_reel_quality(tmp_path, item_metadata={"is_mock": False})
            self.assertFalse(res.is_valid)
            self.assertEqual(res.error_code, "FFPROBE_UNAVAILABLE_OR_FAILED")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_test_demo_media_isolation(self):
        """Verify test/demo/sample assets are rejected in production mode."""
        verifier = InstagramRealVideoVerifier()
        meta_test_req = {"content_id": "test-001", "is_test_mode": False}
        res = verifier.verify_video_file("data/generated_reels/reel_test-video-req.mp4", item_metadata=meta_test_req)
        self.assertFalse(res.is_valid)
        self.assertEqual(res.error_code, "TEST_MEDIA_REJECTED")

    def test_github_raw_canonical_host(self):
        """Verify PublicMediaHost enforces GitHub Raw URL in production mode."""
        os.environ["INSTAGRAM_PRODUCTION_ENABLED"] = "true"
        try:
            host = PublicMediaHost()
            url = host.upload_video("data/owned_reels/cricket_reel_01_reel_916.mp4")
            self.assertTrue(url.startswith("https://raw.githubusercontent.com/"))
        finally:
            os.environ.pop("INSTAGRAM_PRODUCTION_ENABLED", None)

    def test_meta_reel_only_guard(self):
        """Verify InstagramImagePublisher.publish_image fails closed on IMAGE publication."""
        pub = InstagramImagePublisher()
        with self.assertRaises(InstagramError) as cm:
            pub.publish_image("https://example.com/image.jpg")
        self.assertIn("100% Reel-only publishing is enforced", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
