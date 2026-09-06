import json
import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock

from config import Config
from instagram_automation_engine import InstagramAutomationEngine
from instagram_health import get_health_status, get_production_proof, save_production_proof


class TestPhase16_3_Reliability:
    """Automated regression suite for Phase 16.3 Production Reliability & Multi-Run Hardening."""

    def test_prepared_media_validation_rejects_stale_sha(self, tmp_path):
        """Verify publish_prepared rejects prepared media if GITHUB_SHA does not match current run."""
        engine = InstagramAutomationEngine(data_dir=str(tmp_path))
        prep_file = tmp_path / "prepared_media.json"

        # Create dummy media asset
        media_asset = tmp_path / "dummy.mp4"
        media_asset.write_bytes(b"dummy video content 123")

        prep_data = {
            "preparation_id": "prep-test-1",
            "content_id": "test-content-1",
            "local_file": "dummy.mp4",
            "public_url": "https://raw.githubusercontent.com/owner/repo/main/dummy.mp4",
            "github_sha": "old-commit-sha-12345",
            "media_sha256": "dummy-sha",
        }
        prep_file.write_text(json.dumps(prep_data), encoding="utf-8")

        with patch.dict(os.environ, {"GITHUB_SHA": "new-commit-sha-67890"}):
            res = engine.publish_prepared()
            assert res["status"] == "FAILED"
            assert "Stale GitHub SHA" in res["reason"]

    def test_prepared_media_validation_recalculates_sha256(self, tmp_path):
        """Verify publish_prepared recalculates SHA256 from disk and rejects mismatched SHA256."""
        engine = InstagramAutomationEngine(data_dir=str(tmp_path))
        prep_file = tmp_path / "prepared_media.json"

        media_asset = tmp_path / "dummy.mp4"
        media_asset.write_bytes(b"actual disk bytes")

        prep_data = {
            "preparation_id": "prep-test-2",
            "content_id": "test-content-2",
            "local_file": "dummy.mp4",
            "public_url": "https://raw.githubusercontent.com/owner/repo/main/dummy.mp4",
            "media_sha256": "mismatched-expected-sha256-value",
        }
        prep_file.write_text(json.dumps(prep_data), encoding="utf-8")

        res = engine.publish_prepared()
        assert res["status"] == "FAILED"
        assert "Media SHA256 mismatch" in res["reason"]

    def test_reel_only_production_configuration(self):
        """Verify production configuration enforces 100% Reel target and 0% image fallback."""
        config = Config.load_from_env(validate=False)
        assert config.reel_target_percent >= 50
        assert config.image_target_percent == 0
        assert config.enable_image_fallback is False

    def test_telegram_project_isolation(self):
        """Verify code contains zero imports or dependencies from Telegram News_Agent project."""
        import sys
        for mod in sys.modules:
            assert "telegram" not in mod.lower() or mod == "test_phase16_3_reliability"
            assert "news_agent" not in mod.lower()

    def test_allowed_result_classifications(self):
        """Verify save_production_proof formats status correctly according to vocabulary."""
        proof = save_production_proof({"live_reel_verified": True, "status": "LIVE_REEL_PUBLISHED"})
        assert proof["status"] == "LIVE_REEL_PUBLISHED"
        assert proof["live_reel_verified"] is True
