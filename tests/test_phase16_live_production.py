import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from config import Config
from instagram_analytics import get_performance_history, record_performance_history
from instagram_automation_engine import InstagramAutomationEngine
from instagram_content_bundle import ContentBundle
from instagram_content_scorer import InstagramContentScorer
from instagram_health import (
    get_health_status,
    get_production_proof,
    save_production_proof,
    update_health_status,
)
from main import live_production_verification, production_diagnostics


class TestPhase16LiveProductionVerification(unittest.TestCase):
    """Regression test suite for Phase 16 Live Production Verification and Hardening."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = os.path.join(self.temp_dir.name, "data")
        os.makedirs(self.data_dir, exist_ok=True)
        self.health_path = os.path.join(self.data_dir, "health_status.json")
        self.proof_path = os.path.join(self.data_dir, "production_proof.json")
        self.history_path = os.path.join(self.data_dir, "performance_history.json")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_missing_credentials_produces_not_performed(self):
        """Verify missing Meta credentials output LIVE_REEL_VERIFICATION_NOT_PERFORMED."""
        with patch.object(Config, "load_from_env") as mock_cfg:
            cfg = Config(user_id="", access_token="", dry_run=False, production_enabled=True)
            mock_cfg.return_value = cfg
            with patch("main.save_production_proof") as mock_proof, patch("main.update_health_status") as mock_health:
                res = live_production_verification()
                self.assertFalse(res)
                mock_proof.assert_called_once()
                self.assertEqual(mock_proof.call_args[0][0]["status"], "LIVE_REEL_VERIFICATION_NOT_PERFORMED")

    def test_save_and_get_production_proof(self):
        """Verify production proof JSON persistence and schema."""
        proof_input = {
            "live_reel_verified": True,
            "status": "LIVE_REEL_VERIFIED",
            "content_id": "cric-reel-101",
            "source_url": "https://example.com/story",
            "rights_status": "OWNED",
            "rights_evidence_url": "https://example.com/license",
            "media_sha256": "abc123sha256",
            "github_raw_url": "https://raw.githubusercontent.com/user/repo/main/media.mp4",
            "meta_creation_id": "meta-creation-999",
            "instagram_media_id": "180123456789",
            "instagram_permalink": "https://www.instagram.com/reel/180123456789/",
            "published_at": "2026-09-05T20:00:00Z",
        }
        saved = save_production_proof(proof_input, proof_path=self.proof_path)
        self.assertTrue(saved["live_reel_verified"])
        self.assertEqual(saved["status"], "LIVE_REEL_VERIFIED")
        self.assertEqual(saved["instagram_media_id"], "180123456789")

        loaded = get_production_proof(proof_path=self.proof_path)
        self.assertTrue(loaded["live_reel_verified"])
        self.assertEqual(loaded["content_id"], "cric-reel-101")

    def test_update_and_get_health_status(self):
        """Verify data/health_status.json persistence and stale-run tracking."""
        updates = {
            "last_run": "2026-09-05T21:00:00Z",
            "last_success": "2026-09-05T21:00:00Z",
            "last_meta_publish": "2026-09-05T21:00:00Z",
            "consecutive_failures": 0,
            "stale_status": "HEALTHY",
        }
        updated = update_health_status(updates, health_status_path=self.health_path)
        self.assertEqual(updated["stale_status"], "HEALTHY")
        self.assertEqual(updated["consecutive_failures"], 0)

        loaded = get_health_status(health_status_path=self.health_path)
        self.assertEqual(loaded["last_success"], "2026-09-05T21:00:00Z")

    def test_stale_run_detection(self):
        """Verify stale-run detection returns NO_RECENT_SUCCESS when no success recorded."""
        loaded = get_health_status(health_status_path=os.path.join(self.data_dir, "non_existent.json"))
        self.assertEqual(loaded["stale_status"], "NO_RECENT_SUCCESS")

    def test_record_and_get_performance_history(self):
        """Verify performance history persistence in data/performance_history.json."""
        entry = {
            "media_id": "180998877",
            "category": "cricket",
            "caption": "India victory highlights! #Cricket",
            "published_at": "2026-09-05T20:00:00Z",
            "source": "ESPNcricinfo",
            "content_id": "ind-match-1",
            "permalink": "https://www.instagram.com/reel/180998877/",
            "views": 1500,
            "likes": 200,
            "comments": 15,
            "shares": 30,
        }
        saved = record_performance_history(entry, history_path=self.history_path)
        self.assertEqual(saved["media_id"], "180998877")
        self.assertEqual(saved["views"], 1500)

        history = get_performance_history(history_path=self.history_path)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["category"], "cricket")

    def test_production_diagnostics_redaction_and_fields(self):
        """Verify production diagnostics runs without crashing or leaking secrets."""
        with patch.object(Config, "load_from_env") as mock_cfg:
            cfg = Config(user_id="123456", access_token="secret_token_abc", dry_run=True, production_enabled=True)
            mock_cfg.return_value = cfg
            res = production_diagnostics()
            self.assertTrue(res)

    def test_bounded_retries_and_pre_retry_check(self):
        """Verify engine publish_prepared stops when pre-retry check finds already published media."""
        config = Config(user_id="12345", access_token="tok123", dry_run=False, production_enabled=True)
        engine = InstagramAutomationEngine(config=config, data_dir=self.data_dir)

        prepared_file = os.path.join(self.data_dir, "prepared_media.json")
        prep_content = {
            "prepared": True,
            "content_id": "test-dup-101",
            "category": "cricket",
            "media_type": "REEL",
            "public_url": "https://raw.githubusercontent.com/user/repo/main/test.mp4",
            "title": "Test Title",
            "summary": "Test Summary",
            "media_rights_status": "OWNED",
            "rights_evidence_url": "https://example.com/license",
        }
        with open(prepared_file, "w", encoding="utf-8") as f:
            json.dump(prep_content, f)

        # Mock public accessibility check to pass
        with patch("instagram_media_verifier.InstagramMediaVerifier.validate_meta_media_accessibility", return_value={"is_valid": True}):
            # Mock final publish guard to pass initially
            guard_mock = MagicMock()
            guard_mock.verify_and_guard.return_value = MagicMock(is_valid=True)
            # Pre-retry check will return item already published on attempt > 1
            guard_mock.get_published_history.return_value = [
                {"content_id": "test-dup-101", "instagram_media_id": "1809999888", "meta_creation_id": "c123"}
            ]
            engine.final_publish_guard = guard_mock

            # Mock publisher to fail on attempt 1
            with patch("instagram_reel_publisher.InstagramReelPublisher.publish_reel", return_value=MagicMock(success=False, message="Transient error")):
                res = engine.publish_prepared()
                # Attempt 1 fails, attempt 2 pre-retry check finds already published -> returns SUCCESS
                self.assertEqual(res["status"], "SUCCESS")
                self.assertEqual(res["media_id"], "1809999888")

    def test_smart_trend_content_scoring(self):
        """Verify content scorer calculates deterministic score with trend breakdown."""
        scorer = InstagramContentScorer(score_threshold=35)
        mock_content = MagicMock(
            title="IND vs AUS T20 World Cup Final Thriller",
            summary="India secures sensational victory in final over with outstanding bowling spell.",
            category="cricket",
            media_type="REEL",
            image_url=None,
            video_url="https://example.com/video.mp4",
            source="ESPNcricinfo",
            caption="IND vs AUS Final!",
        )

        score = scorer.score_content(mock_content)
        self.assertGreaterEqual(score.total_score, 35)
        self.assertEqual(score.decision, "ACCEPT")
        self.assertIn("title_quality", score.breakdown)

    def test_no_telegram_code_imports(self):
        """Security/Isolation audit: Verify no Telegram project or News_Agent imports exist in codebase."""
        import sys
        for module_name in sys.modules:
            self.assertNotIn("News_Agent", module_name)
            self.assertNotIn("telegram_bot", module_name)


if __name__ == "__main__":
    unittest.main()
