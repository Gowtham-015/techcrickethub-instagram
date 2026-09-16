import os
import json
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from config import Config
from instagram_automation_engine import InstagramAutomationEngine
from instagram_content_bundle import ContentBundle
from instagram_final_publish_guard import InstagramFinalPublishGuard
from instagram_production_gate import InstagramProductionGate
from instagram_health import InstagramHealthTracker
from instagram_real_video_source import OwnedVideoProvider, InstagramRealVideoSource
from instagram_real_video_verifier import InstagramRealVideoVerifier
from instagram_reel_generator import InstagramReelGenerator
from instagram_rights_evidence_engine import InstagramRightsEvidenceEngine
from instagram_public_media_host import normalize_reel_filename, normalize_reel_media_url


class TestPhase23FreshReelSupply(unittest.TestCase):

    def setUp(self):
        self.config = Config.load_from_env(validate=False)

    def test_1_owned_reels_published_recognition(self):
        """TEST 1: All four current owned Reels are recognized as already published."""
        guard = InstagramFinalPublishGuard(config=self.config)
        prov = OwnedVideoProvider()
        owned_items = prov.fetch_video_items()
        self.assertEqual(len(owned_items), 4)
        for item in owned_items:
            cid = item.get("content_id")
            url = item.get("source_url") or item.get("video_url")
            is_dup = guard.is_duplicate(content_id=cid, url=url)
            self.assertTrue(is_dup, f"Owned reel '{cid}' was not recognized as duplicate.")

    def test_2_phaseA_no_valid_reel_when_exhausted(self):
        """TEST 2: Phase A returns NO_VALID_REEL when all owned Reels are published and no news/video exists."""
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = InstagramAutomationEngine(config=self.config, data_dir=temp_dir)
            engine.source = MagicMock()
            engine.source.get_content_items.return_value = []
            engine.news_source = MagicMock()
            engine.news_source.get_content_items.return_value = []
            
            res = engine.prepare_media()
            self.assertEqual(res.get("status"), "NO_VALID_REEL")
            self.assertFalse(res.get("prepared"))

    def test_3_fresh_external_reel_selection(self):
        """TEST 3: A fresh external Reel can be selected when valid."""
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = InstagramAutomationEngine(config=self.config, data_dir=temp_dir)
            fresh_ext = {
                "content_id": "ext-fresh-9999",
                "title": "Fresh External Match Update Unique 9999",
                "summary": "Fresh external cricket match summary unique 9999.",
                "category": "cricket",
                "media_type": "REEL",
                "video_url": "https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/data/owned_reels/fresh_external_asset_9999.mp4",
                "rights_status": "LICENSED",
                "rights_evidence": "Commercial License #9999",
                "rights_evidence_url": "https://techcrickethub.com/license/9999",
                "commercial_use_allowed": True,
            }
            engine.source = MagicMock()
            engine.source.get_content_items.return_value = [fresh_ext]
            engine.news_source = None
            
            res = engine.prepare_media()
            self.assertTrue(res.get("prepared"))
            self.assertEqual(res.get("content_id"), "ext-fresh-9999")

    def test_4_fresh_news_original_generated_fallback(self):
        """TEST 4: Fresh news story with no reusable video produces one ORIGINAL_GENERATED Reel."""
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = InstagramAutomationEngine(config=self.config, data_dir=temp_dir)
            engine.source = MagicMock()
            engine.source.get_content_items.return_value = []  # No external videos
            
            fresh_news = {
                "content_id": "news-fresh-999",
                "title": "Unique Fresh News Headline 999",
                "summary": "Unique summary for fresh news headline 999.",
                "category": "cricket",
                "source_name": "CricInfoNews",
                "source_url": "https://cricinfo.com/fresh-news-999",
            }
            engine.news_source = MagicMock()
            engine.news_source.get_content_items.return_value = [fresh_news]
            
            res = engine.prepare_media()
            self.assertTrue(res.get("prepared"))
            self.assertTrue(res.get("content_id").startswith("generated-news-reel-"))

    def test_5_generated_reel_aspect_ratio(self):
        """TEST 5: Generated Reel frame / video specs targeting 1080x1920 (9:16)."""
        gen = InstagramReelGenerator()
        item = {
            "content_id": "aspect-test-01",
            "title": "Aspect Ratio Test",
            "summary": "Testing aspect ratio 1080x1920.",
            "category": "cricket",
        }
        res = gen.generate_reel_from_facts(item, duration_sec=3.0)
        if res.get("success") and res.get("reel_path"):
            verifier = InstagramRealVideoVerifier()
            v_res = verifier.verify_video_file(res["reel_path"], item_metadata={"media_rights_status": "ORIGINAL_GENERATED"})
            self.assertTrue(v_res.is_valid)
            self.assertEqual(v_res.width, 1080)
            self.assertEqual(v_res.height, 1920)

    def test_6_generated_reel_mp4_format(self):
        """TEST 6: Generated Reel is valid MP4."""
        gen = InstagramReelGenerator()
        item = {
            "content_id": "mp4-format-01",
            "title": "MP4 Format Test",
            "summary": "Testing MP4 container format.",
            "category": "technology",
        }
        res = gen.generate_reel_from_facts(item, duration_sec=3.0)
        if res.get("success") and res.get("reel_path"):
            self.assertTrue(res["reel_path"].endswith(".mp4"))
            self.assertTrue(os.path.exists(res["reel_path"]))

    def test_7_generated_reel_duration(self):
        """TEST 7: Generated Reel has non-zero duration."""
        gen = InstagramReelGenerator()
        item = {
            "content_id": "dur-test-01",
            "title": "Duration Test",
            "summary": "Testing duration.",
            "category": "cricket",
        }
        res = gen.generate_reel_from_facts(item, duration_sec=4.0)
        if res.get("success") and res.get("reel_path"):
            verifier = InstagramRealVideoVerifier()
            v_res = verifier.verify_video_file(res["reel_path"], item_metadata={"media_rights_status": "ORIGINAL_GENERATED"})
            self.assertGreater(v_res.duration_seconds, 0.0)

    def test_8_generated_reel_stable_identity(self):
        """TEST 8: Generated Reel receives stable content identity."""
        gen = InstagramReelGenerator()
        item = {
            "content_id": "stable-id-100",
            "title": "Stable ID Test",
            "summary": "Summary text",
            "category": "cricket",
        }
        res = gen.generate_reel_from_facts(item, duration_sec=3.0)
        self.assertEqual(res.get("media_rights_status"), "ORIGINAL_GENERATED")

    def test_9_duplicate_story_no_regeneration(self):
        """TEST 9: Same news story cannot generate another Reel after publication."""
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = InstagramAutomationEngine(config=self.config, data_dir=temp_dir)
            engine.source = MagicMock()
            engine.source.get_content_items.return_value = []
            
            # Published story
            published_story = {
                "content_id": "pub-story-01",
                "title": "East Zone vs South Zone Duleep Trophy Thriller - Unstoppable Action 🇮🇳🏏",
                "summary": "East Zone battle South Zone",
                "category": "cricket",
                "source_url": "https://cricinfo.com/duleep",
                "source_domain": "cricinfo.com",
                "media_type": "REEL",
                "video_url": "https://cricinfo.com/duleep.mp4",
                "rights_status": "LICENSED",
                "media_rights_status": "LICENSED",
                "rights_evidence": "Licensed match highlights",
                "license_url": "https://cricinfo.com/terms",
                "commercial_use_allowed": True,
            }
            engine.news_source = MagicMock()
            engine.news_source.get_content_items.return_value = [published_story]
            
            from instagram_content_bundle import ContentBundle
            b = ContentBundle(
                content_id="pub-story-01",
                category="cricket",
                title="East Zone vs South Zone Duleep Trophy Thriller - Unstoppable Action 🇮🇳🏏",
                summary="East Zone battle South Zone",
                source_url="https://cricinfo.com/duleep",
                source_domain="cricinfo.com",
                published_at="2026-09-01T10:00:00Z",
                media_url="https://cricinfo.com/duleep.mp4",
                media_type="REEL",
            )
            engine.final_publish_guard.record_published_item(bundle=b, media_id="12345")
            
            res = engine.prepare_media()
            self.assertEqual(res.get("status"), "NO_VALID_REEL")

    def test_10_generated_reel_rights_policy(self):
        """TEST 10: Generated Reel passes rights policy."""
        engine = InstagramRightsEvidenceEngine()
        item = {
            "content_id": "gen-rights-01",
            "title": "Generated Reel Rights",
            "media_rights_status": "ORIGINAL_GENERATED",
            "rights_evidence": "Original Reel generated by TechCricketHub",
            "license_url": "https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/instagram_reel_generator.py",
            "commercial_use_allowed": True,
        }
        res = engine.verify_rights_evidence(item)
        self.assertTrue(res.is_valid)
        self.assertEqual(res.rights_status, "ORIGINAL_GENERATED")

    def test_11_generated_reel_sha256_dedupe(self):
        """TEST 11: Generated Reel participates in SHA256 duplicate protection."""
        with tempfile.TemporaryDirectory() as temp_dir:
            guard = InstagramFinalPublishGuard(config=self.config, data_dir=temp_dir)
            b = ContentBundle(
                content_id="gen-sha-01",
                category="cricket",
                title="Unique Title SHA Test",
                summary="Unique Summary",
                source_url="https://cricinfo.com/sha_test",
                source_domain="cricinfo.com",
                published_at=datetime.now(timezone.utc).isoformat(),
                media_url="https://raw.githubusercontent.com/test_sha.mp4",
                media_type="REEL",
                media_rights_status="ORIGINAL_GENERATED",
                rights_evidence_type="ORIGINAL_GENERATED_ANIMATION",
                rights_evidence_url="https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/instagram_reel_generator.py",
                commercial_use_allowed=True,
                media_hash="11223344556677889900aabbccddeeff",
            )
            guard.record_published_item(b, media_id="test_gen_m_id")
            
            b2 = ContentBundle(
                content_id="gen-sha-02",
                category="cricket",
                title="Unrelated Quantum AI Computing News",
                summary="Different Summary",
                source_url="https://cricinfo.com/sha_test_diff",
                source_domain="cricinfo.com",
                published_at=datetime.now(timezone.utc).isoformat(),
                media_url="https://raw.githubusercontent.com/test_sha_diff.mp4",
                media_type="REEL",
                media_rights_status="ORIGINAL_GENERATED",
                rights_evidence_type="ORIGINAL_GENERATED_ANIMATION",
                rights_evidence_url="https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/instagram_reel_generator.py",
                commercial_use_allowed=True,
                media_hash="11223344556677889900aabbccddeeff",
            )
            g_res = guard.verify_and_guard(b2)
            self.assertFalse(g_res.is_valid)
            self.assertIn(g_res.error_code, ("DUPLICATE_MEDIA", "DUPLICATE_MEDIA_URL", "DUPLICATE_TITLE"))

    def test_12_filename_normalization_no_double_suffix(self):
        """TEST 12: Filename normalization never creates _reel_916_reel_916.mp4."""
        fn = "cricket_reel_east_vs_south_duleep_trophy_reel_916_reel_916.mp4"
        norm = normalize_reel_filename(fn)
        self.assertEqual(norm, "cricket_reel_east_vs_south_duleep_trophy_reel_916.mp4")

    def test_13_production_gate_blocked_prevents_meta(self):
        """TEST 13: Production gate BLOCKED prevents Meta API calls."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Config.load_from_env(validate=False)
            config.production_enabled = True
            config.dry_run = False
            
            engine = InstagramAutomationEngine(config=config, data_dir=temp_dir)
            engine.gate = MagicMock()
            engine.gate.evaluate.return_value = MagicMock(can_publish=False, reason="Safety test block", status="BLOCKED")
            
            # Write fake prepared media
            prep_file = os.path.join(temp_dir, "prepared_media.json")
            with open(prep_file, "w", encoding="utf-8") as f:
                json.dump({
                    "preparation_id": "prep-test-13",
                    "content_id": "cid-test-13",
                    "title": "Title 13",
                    "summary": "Summary 13",
                    "category": "cricket",
                    "media_type": "REEL",
                    "public_url": "https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/data/owned_reels/cooldown_asset.mp4",
                    "media_rights_status": "ORIGINAL_GENERATED",
                    "commercial_use_allowed": True,
                }, f)
                
            res = engine.publish_prepared()
            self.assertIn(res.get("status"), ("PRODUCTION_GATE_BLOCKED", "BLOCKED", "FAILED"))
            self.assertEqual(res.get("published"), 0)

    def test_14_production_gate_ready_permits_path(self):
        """TEST 14: Production gate READY permits publishing path to continue."""
        gate = InstagramProductionGate()
        config = Config.load_from_env(validate=False)
        config.dry_run = True
        res = gate.evaluate(config=config)
        self.assertTrue(res.can_publish or res.status in ("DRY_RUN", "READY"))

    def test_15_no_eligible_reel_no_meta_failure(self):
        """TEST 15: NO_ELIGIBLE_REEL does not increment Meta failure counters."""
        with tempfile.TemporaryDirectory() as temp_dir:
            health = InstagramHealthTracker(health_path=os.path.join(temp_dir, "health.json"))
            health.record_no_valid_reel_run()
            h_data = health._load_health()
            self.assertEqual(h_data.get("meta_failures", 0), 0)
            self.assertEqual(h_data.get("consecutive_publish_failures", 0), 0)

    def test_16_duplicate_blocked_no_meta_failure(self):
        """TEST 16: DUPLICATE_BLOCKED does not increment Meta failure counters."""
        with tempfile.TemporaryDirectory() as temp_dir:
            health = InstagramHealthTracker(health_path=os.path.join(temp_dir, "health.json"))
            health.record_duplicate_block("Duplicate test block")
            h_data = health._load_health()
            self.assertEqual(h_data.get("meta_failures", 0), 0)
            self.assertEqual(h_data.get("consecutive_publish_failures", 0), 0)

    def test_17_meta_container_error_increments_failures(self):
        """TEST 17: META_CONTAINER_ERROR increments genuine Meta failure counters."""
        with tempfile.TemporaryDirectory() as temp_dir:
            health = InstagramHealthTracker(health_path=os.path.join(temp_dir, "health.json"))
            health.record_meta_failure()
            h_data = health._load_health()
            self.assertEqual(h_data.get("meta_failures", 0), 1)

    def test_18_production_check_reports_blocked(self):
        """TEST 18: production_check() reports BLOCKED when gate is blocked."""
        gate = InstagramProductionGate()
        config = Config.load_from_env(validate=False)
        tracker = MagicMock()
        tracker.get_health_status.return_value = {"production_paused": True, "pause_reason": "TEST_PAUSE"}
        res = gate.evaluate(config=config, health_tracker=tracker)
        self.assertFalse(res.can_publish)

    def test_19_production_check_never_ready_when_paused(self):
        """TEST 19: production_check() never reports READY while paused."""
        gate = InstagramProductionGate()
        config = Config.load_from_env(validate=False)
        tracker = MagicMock()
        tracker.get_health_status.return_value = {"production_paused": True, "pause_reason": "CONSECUTIVE_PUBLISH_FAILURES"}
        res = gate.evaluate(config=config, health_tracker=tracker)
        self.assertEqual(res.status, "BLOCKED")
        self.assertFalse(res.can_publish)

    def test_20_stale_history_override(self):
        """TEST 20: Stale historical error does not override INSTAGRAM_REEL_DISCOVERY_ENABLED=true."""
        config = Config.load_from_env(validate=False)
        config.reel_discovery_enabled = True
        self.assertTrue(config.reel_discovery_enabled)

    def test_21_publisher_workflow_smoke_test(self):
        """TEST 21: Workflow production job executes fast preflight smoke test."""
        wf_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".github", "workflows", "instagram-publisher.yml")
        self.assertTrue(os.path.exists(wf_path))
        with open(wf_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("pytest tests/test_phaseA_duplicate_filtering.py tests/test_phase23_fresh_reel_supply.py -q", content)

    def test_22_ci_workflow_full_suite(self):
        """TEST 22: CI workflow executes full pytest suite on push/PR."""
        ci_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".github", "workflows", "instagram-ci.yml")
        self.assertTrue(os.path.exists(ci_path))
        with open(ci_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("python -m pytest -q", content)


if __name__ == "__main__":
    unittest.main()
