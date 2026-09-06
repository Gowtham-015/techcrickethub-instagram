import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from config import Config
from instagram_automation_engine import InstagramAutomationEngine
from instagram_real_video_verifier import InstagramRealVideoVerifier, RealVideoVerificationResult
from instagram_rights_evidence_engine import InstagramRightsEvidenceEngine, RightsVerificationResult


class TestPhase18RealVideoAndRights(unittest.TestCase):
    """Comprehensive test suite for Phase 18 Real Video Discovery & Rights Evidence Engine."""

    def setUp(self):
        self.config = Config.load_from_env(validate=False)
        self.config.dry_run = True
        self.rights_engine = InstagramRightsEvidenceEngine()
        self.video_verifier = InstagramRealVideoVerifier()

    def test_missing_rights_evidence_rejection(self):
        """Verify candidate with missing rights status is rejected."""
        item = {
            "content_id": "cand-no-rights",
            "title": "Unlicensed Video Post",
            "media_rights_status": "RIGHTS_EVIDENCE_MISSING",
        }
        res = self.rights_engine.verify_rights_evidence(item)
        self.assertFalse(res.is_valid)
        self.assertIn("RIGHTS_EVIDENCE_MISSING", res.rights_status)
        self.assertTrue(len(res.reasons) > 0)

    def test_false_and_ambiguous_rights_rejection(self):
        """Verify candidate with ambiguous rights or non-commercial restriction is rejected."""
        item_false = {
            "content_id": "cand-false-rights",
            "title": "Match Highlights Video",
            "media_rights_status": "FALSE_RIGHTS",
            "commercial_use_allowed": True,
        }
        res_false = self.rights_engine.verify_rights_evidence(item_false)
        self.assertFalse(res_false.is_valid)

        item_non_comm = {
            "content_id": "cand-non-comm",
            "title": "Non Commercial Video",
            "media_rights_status": "VERIFIED_CC_LICENSE",
            "commercial_use_allowed": False,
        }
        res_non_comm = self.rights_engine.verify_rights_evidence(item_non_comm)
        self.assertFalse(res_non_comm.is_valid)

    def test_corrupted_video_rejection(self):
        """Verify empty (0-byte) or non-existent file is rejected as corrupted video."""
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            # 0 bytes file
            res = self.video_verifier.verify_video_file(tmp_path)
            self.assertFalse(res.is_valid)
            self.assertTrue(res.is_corrupted)
            self.assertEqual(res.error_code, "CORRUPTED_VIDEO")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_html_disguised_as_mp4_rejection(self):
        """Verify HTML document saved with .mp4 extension is rejected."""
        with tempfile.NamedTemporaryFile(suffix=".mp4", mode="w", encoding="utf-8", delete=False) as tmp:
            tmp.write("<!DOCTYPE html><html><head><title>404 Not Found</title></head><body>Error 404</body></html>")
            tmp_path = tmp.name

        try:
            res = self.video_verifier.verify_video_file(tmp_path)
            self.assertFalse(res.is_valid)
            self.assertTrue(res.is_html)
            self.assertEqual(res.error_code, "HTML_DISGUISED_AS_VIDEO")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_image_disguised_as_mp4_rejection(self):
        """Verify image file disguised with .mp4 extension is rejected."""
        with tempfile.NamedTemporaryFile(suffix=".mp4", mode="wb", delete=False) as tmp:
            # JPEG magic bytes: \xFF\xD8\xFF
            tmp.write(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00")
            tmp_path = tmp.name

        try:
            res = self.video_verifier.verify_video_file(tmp_path)
            self.assertFalse(res.is_valid)
            self.assertEqual(res.error_code, "IMAGE_TO_VIDEO_REJECTED")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_valid_owned_real_video_verification(self):
        """Verify valid owned/licensed MP4 video file passes technical & rights verification."""
        item = {
            "content_id": "cand-valid-owned",
            "title": "Valid Owned Real Video",
            "media_rights_status": "OWNED",
            "rights_evidence": "PROPRIETARY_OWNERSHIP",
            "commercial_use_allowed": True,
        }
        rights_res = self.rights_engine.verify_rights_evidence(item)
        self.assertTrue(rights_res.is_valid)

        with tempfile.NamedTemporaryFile(suffix=".mp4", mode="wb", delete=False) as tmp:
            # Construct synthetic MP4 header with ftyp box
            tmp.write(b"\x00\x00\x00\x1cftypisom\x00\x00\x02\x00isomiso2avc1mp41" + b"\x00" * 1024)
            tmp_path = tmp.name

        try:
            video_res = self.video_verifier.verify_video_file(tmp_path, item)
            self.assertTrue(video_res.is_valid)
            self.assertTrue(video_res.video_stream_exists)
            self.assertEqual(video_res.error_code, "SUCCESS")
            self.assertTrue(len(video_res.media_sha256) == 64)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_end_to_end_prepare_media_rejects_missing_rights(self):
        """Verify InstagramAutomationEngine.prepare_media rejects candidates with missing rights evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = Config.load_from_env(validate=False)
            config.dry_run = True
            config.reel_discovery_enabled = True
            auto_engine = InstagramAutomationEngine(config=config, data_dir=tmp_dir)
            auto_engine.news_source = None

            cands = [
                {
                    "content_id": "cand-bad-rights",
                    "title": "Video Without Item-Level Rights",
                    "summary": "This candidate lacks rights evidence.",
                    "category": "cricket",
                    "media_type": "REEL",
                    "video_url": "https://example.com/bad.mp4",
                    "media_rights_status": "RIGHTS_EVIDENCE_MISSING",
                    "source_domain": "espncricinfo.com",
                }
            ]

            with patch.object(auto_engine.source, "get_content_items", return_value=cands):
                res = auto_engine.prepare_media()
                self.assertFalse(res.get("prepared"))
                self.assertEqual(res.get("status"), "NO_CANDIDATES")


if __name__ == "__main__":
    unittest.main()
