import json
import os
import tempfile
import unittest
from datetime import datetime, timezone, timedelta

from config import Config
from instagram_factual_caption_engine import InstagramFactualCaptionEngine
from instagram_final_publish_guard import InstagramFinalPublishGuard, GuardResult
from instagram_content_bundle import ContentBundle
from instagram_real_video_source import OwnedVideoProvider
from instagram_rights_evidence_engine import InstagramRightsEvidenceEngine
from main import run_production_smoke_test, validate_owned_media


class TestPhase21ProductionHardening(unittest.TestCase):
    """Comprehensive unit test suite for Phase 21 Production Hardening."""

    def setUp(self):
        self.config = Config.load_from_env(validate=False)
        self.rights_engine = InstagramRightsEvidenceEngine()
        self.caption_engine = InstagramFactualCaptionEngine(token=self.config.access_token)

    def test_production_smoke_test_runner(self):
        """Verify python main.py --production-smoke-test completes in < 30s with PASS."""
        res = run_production_smoke_test()
        self.assertTrue(res)

    def test_owned_media_manifest_validation(self):
        """Verify --validate-owned-media validates all 4 manifest items cleanly."""
        res = validate_owned_media()
        self.assertTrue(res)

    def test_fail_closed_rights_engine_missing_fields(self):
        """Verify fail-closed rights checks reject items with missing rights fields."""
        missing_comm = {
            "title": "Test Reel",
            "rights_status": "OWNED",
            "rights_evidence": "Account-owned",
            "rights_evidence_url": "file:///path",
            "license": "Owned",
            "commercial_use_allowed": False,
        }
        res_comm = self.rights_engine.verify_rights_evidence(missing_comm)
        self.assertFalse(res_comm.is_valid)
        self.assertFalse(res_comm.commercial_use_allowed)

        unknown_status = {
            "title": "Test Reel",
            "rights_status": "UNKNOWN",
        }
        res_unk = self.rights_engine.verify_rights_evidence(unknown_status)
        self.assertFalse(res_unk.is_valid)

    def test_generic_media_visual_disclaimer(self):
        """Verify media_event_match=False emits neutral visual disclaimer."""
        cap_res = self.caption_engine.generate_factual_caption(
            title="India Wins T20 Match Against Sri Lanka",
            summary="Team India put up a dominant bowling display in the final overs.",
            category="cricket",
            media_event_match=False,
        )
        self.assertTrue(cap_res.is_valid)
        self.assertIn("Visual: TechCricketHub original cricket Reel.", cap_res.caption)

    def test_story_fingerprint_duplicate_detection(self):
        """Verify FinalPublishGuard blocks duplicate story fingerprints."""
        with tempfile.TemporaryDirectory() as temp_dir:
            guard = InstagramFinalPublishGuard(config=self.config, data_dir=temp_dir)

            b1 = ContentBundle(
                content_id="story-101",
                category="cricket",
                title="BCCI Announces Squad For Asia Cup",
                summary="Key players return to team camp after rehabilitation.",
                source_url="https://cricinfo.com/story1_unique_test",
                source_domain="cricinfo.com",
                published_at=datetime.now(timezone.utc).isoformat(),
                media_url="https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/data/owned_reels/cricket_reel_01.mp4",
                media_type="REEL",
                media_rights_status="OWNED",
                rights_evidence_type="ACCOUNT_OWNED_METADATA",
                rights_evidence_url="https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/data/owned_reels/metadata.json",
                commercial_use_allowed=True,
                caption="🏆 BCCI Announces Squad For Asia Cup\n\nKey players return to team camp.\n\n📌 Key Takeaway: Verified source reports Key players return.\n\n💬 What are your thoughts?",
            )

            g_res = guard.verify_and_guard(b1)
            self.assertTrue(g_res.is_valid, msg=f"b1 failed guard: {g_res.message}")

            # Record b1 into history
            guard.record_published_item(b1, media_id="test_media_id_101")

            # Try registering b2 with identical story fingerprint
            b2 = ContentBundle(
                content_id="story-102",
                category="cricket",
                title="BCCI Announces Squad For Asia Cup",
                summary="Key players return to team camp after rehabilitation.",
                source_url="https://cricinfo.com/story2_unique_test",
                source_domain="cricinfo.com",
                published_at=datetime.now(timezone.utc).isoformat(),
                media_url="https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/data/owned_reels/cricket_reel_02.mp4",
                media_type="REEL",
                media_rights_status="OWNED",
                rights_evidence_type="ACCOUNT_OWNED_METADATA",
                rights_evidence_url="https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/data/owned_reels/metadata.json",
                commercial_use_allowed=True,
                caption="🏆 BCCI Announces Squad For Asia Cup\n\nKey players return to team camp.\n\n📌 Key Takeaway: Verified source reports Key players return.\n\n💬 What are your thoughts?",
            )

            g_res2 = guard.verify_and_guard(b2)
            self.assertFalse(g_res2.is_valid)
            self.assertIn(g_res2.error_code, ("DUPLICATE_STORY", "DUPLICATE_TITLE", "DUPLICATE_SOURCE"))

    def test_media_rotation_cooldown(self):
        """Verify FinalPublishGuard blocks media asset used within last N posts."""
        with tempfile.TemporaryDirectory() as temp_dir:
            guard = InstagramFinalPublishGuard(config=self.config, data_dir=temp_dir)

            media_url = "https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/data/owned_reels/cooldown_asset.mp4"

            b1 = ContentBundle(
                content_id="cd-101",
                category="cricket",
                title="First Match Headline Update Unique",
                summary="Summary text for first match update.",
                source_url="https://cricinfo.com/match1_unique_test",
                source_domain="cricinfo.com",
                published_at=datetime.now(timezone.utc).isoformat(),
                media_url=media_url,
                media_type="REEL",
                media_rights_status="OWNED",
                rights_evidence_type="ACCOUNT_OWNED_METADATA",
                rights_evidence_url="https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/data/owned_reels/metadata.json",
                commercial_use_allowed=True,
                caption="🏆 First Match Headline Update Unique\n\nSummary text for first match update.\n\n📌 Key Takeaway: First match.\n\n💬 Comments?",
            )

            guard.record_published_item(b1, media_id="test_m_id_cd1")

            b2 = ContentBundle(
                content_id="cd-102",
                category="cricket",
                title="Apple Unveils New Silicon Processor Architecture",
                summary="Summary text for tech update with completely different content.",
                source_url="https://cricinfo.com/match2_unique_test",
                source_domain="cricinfo.com",
                published_at=datetime.now(timezone.utc).isoformat(),
                media_url=media_url,
                media_type="REEL",
                media_rights_status="OWNED",
                rights_evidence_type="ACCOUNT_OWNED_METADATA",
                rights_evidence_url="https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/data/owned_reels/metadata.json",
                commercial_use_allowed=True,
                caption="🏆 Apple Unveils New Silicon Processor Architecture\n\nSummary text for tech update.\n\n📌 Key Takeaway: Tech news.\n\n💬 Comments?",
            )

            g_res = guard.verify_and_guard(b2)
            self.assertFalse(g_res.is_valid)
            self.assertEqual(g_res.error_code, "MEDIA_COOLDOWN")


if __name__ == "__main__":
    unittest.main()
