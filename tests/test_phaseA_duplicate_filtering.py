import os
import json
import tempfile
import pytest
from unittest.mock import MagicMock, patch

from config import Config
from instagram_automation_engine import InstagramAutomationEngine
from instagram_real_video_source import InstagramRealVideoSource
from instagram_health import InstagramHealthTracker


class TestPhaseADuplicateFiltering:

    @pytest.fixture
    def setup_env(self, tmp_path):
        """Sets up isolated test environment with temporary data directory."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        owned_dir = data_dir / "owned_reels"
        owned_dir.mkdir()

        # Create dummy video files
        v1 = owned_dir / "cricket_reel_east_vs_south_duleep_trophy_reel_916.mp4"
        v1.write_bytes(b"dummy video bytes 1")
        v2 = owned_dir / "cricket_reel_ind_vs_pak_women_reel_916.mp4"
        v2.write_bytes(b"dummy video bytes 2")

        metadata_content = {
            "items": [
                {
                    "file": "cricket_reel_east_vs_south_duleep_trophy_reel_916.mp4",
                    "content_id": "owned-cricket-duleep-trophy-01",
                    "title": "East Zone vs South Zone Duleep Trophy Thriller - Unstoppable Action",
                    "summary": "East Zone battle South Zone in a high-voltage Duleep Trophy clash",
                    "category": "cricket",
                    "publisher": "TechCricketHub",
                    "rights_status": "OWNED",
                    "rights_evidence": "Account-owned original cricket media asset",
                    "rights_evidence_url": "data/owned_reels/metadata.json",
                    "license": "Owned by TechCricketHub",
                    "commercial_use_allowed": True,
                    "modification_allowed": True,
                },
                {
                    "file": "cricket_reel_ind_vs_pak_women_reel_916.mp4",
                    "content_id": "owned-cricket-ind-vs-pak-women-01",
                    "title": "India vs Pakistan Women Cricket Showdown - High Voltage Thriller",
                    "summary": "India clash with Pakistan in an intense Women's Cricket match",
                    "category": "cricket",
                    "publisher": "TechCricketHub",
                    "rights_status": "OWNED",
                    "rights_evidence": "Account-owned original cricket media asset",
                    "rights_evidence_url": "data/owned_reels/metadata.json",
                    "license": "Owned by TechCricketHub",
                    "commercial_use_allowed": True,
                    "modification_allowed": True,
                }
            ]
        }
        (owned_dir / "metadata.json").write_text(json.dumps(metadata_content), encoding="utf-8")

        v1_str = str(v1).replace("\\", "/")
        v2_str = str(v2).replace("\\", "/")

        published_history = {
            "items": [
                {
                    "instagram_media_id": "18074199965428937",
                    "content_id": "ownedvideo-297604c7883f3d3f",
                    "canonical_source_url": f"file:///{v1_str}",
                    "title": "East Zone vs South Zone Duleep Trophy Thriller - Unstoppable Action",
                    "normalized_title": "east zone vs south zone duleep trophy thriller unstoppable action",
                    "media_url": f"https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/data/owned_reels/cricket_reel_east_vs_south_duleep_trophy_reel_916.mp4",
                    "category": "cricket",
                    "media_type": "REEL",
                    "published_at": "2026-09-06T18:53:56.657567+00:00",
                    "status": "PUBLISHED"
                }
            ]
        }
        (data_dir / "instagram_published_history.json").write_text(json.dumps(published_history), encoding="utf-8")

        cfg = Config.load_from_env(validate=False)
        cfg.production_enabled = False
        cfg.dry_run = True
        cfg.reel_discovery_enabled = False
        engine = InstagramAutomationEngine(config=cfg, data_dir=str(data_dir))
        engine.news_source = None
        engine.source = None
        return engine, data_dir, v1, v2

    def test_A_published_reel_excluded_during_candidate_selection(self, setup_env):
        """Test A: Verifies that already-published reel (Duleep Trophy) is excluded in Phase A."""
        engine, data_dir, v1, v2 = setup_env
        
        # Run prepare_media
        with patch.object(engine.real_video_verifier, "verify_video_file") as mock_v_ver, \
             patch.object(engine.reel_quality_engine, "validate_reel_quality") as mock_q_ver:
            mock_v_ver.return_value = MagicMock(is_valid=True, duration_seconds=15.0, media_sha256="hash2")
            mock_q_ver.return_value = MagicMock(is_valid=True, duration_seconds=15.0)

            res = engine.prepare_media()

        # The published Duleep Trophy reel should be skipped, and the unpublished Ind vs Pak Women reel should be selected
        assert res.get("prepared") is True
        assert res.get("status") == "PREPARED"
        assert "ind_vs_pak" in res.get("local_file", "").lower() or "ind_vs_pak" in res.get("public_url", "").lower()

    def test_B_next_unpublished_reel_is_selected(self, setup_env):
        """Test B: Verifies that when the first candidate is published, the next unpublished candidate is selected."""
        engine, data_dir, v1, v2 = setup_env

        with patch.object(engine.real_video_verifier, "verify_video_file") as mock_v_ver, \
             patch.object(engine.reel_quality_engine, "validate_reel_quality") as mock_q_ver:
            mock_v_ver.return_value = MagicMock(is_valid=True, duration_seconds=15.0, media_sha256="hash2")
            mock_q_ver.return_value = MagicMock(is_valid=True, duration_seconds=15.0)

            res = engine.prepare_media()

        assert res.get("prepared") is True
        # Ind vs Pak Women reel was prepared
        with open(data_dir / "prepared_media.json", "r", encoding="utf-8") as f:
            prep_data = json.load(f)
        assert "ind_vs_pak" in prep_data.get("local_file", "").lower()

    def test_C_all_reels_published_returns_controlled_no_content(self, setup_env):
        """Test C: Verifies that when ALL available reels are published, a controlled no-content result is returned."""
        engine, data_dir, v1, v2 = setup_env

        v2_str = str(v2).replace("\\", "/")
        # Add second reel to published history as well
        pub_file = data_dir / "instagram_published_history.json"
        with open(pub_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["items"].append({
            "instagram_media_id": "18213902644346055",
            "content_id": "owned-cricket-ind-vs-pak-women-01",
            "canonical_source_url": f"file:///{v2_str}",
            "title": "India vs Pakistan Women Cricket Showdown - High Voltage Thriller",
            "normalized_title": "india vs pakistan women cricket showdown high voltage thriller",
            "media_url": f"https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/data/owned_reels/cricket_reel_ind_vs_pak_women_reel_916.mp4",
            "category": "cricket",
            "media_type": "REEL",
            "published_at": "2026-09-07T10:54:00.117426+00:00",
            "status": "PUBLISHED"
        })
        with open(pub_file, "w", encoding="utf-8") as f:
            json.dump(data, f)

        res = engine.prepare_media()

        # Should return controlled NO_VALID_REEL result without error
        assert res.get("prepared") is False
        assert res.get("status") in ("NO_VALID_REEL", "NO_ELIGIBLE_REELS")
        assert not (data_dir / "prepared_media.json").exists()

    def test_D_phase_B_C_blocks_race_condition_duplicate(self, setup_env):
        """Test D: Verifies Phase B/C final publish guard blocks publication if item was published in parallel."""
        engine, data_dir, v1, v2 = setup_env
        import hashlib
        v1_sha = hashlib.sha256(v1.read_bytes()).hexdigest()

        # Create a prepared media JSON pointing to v1
        prep_data = {
            "preparation_id": "prep-test-1234",
            "content_id": "owned-cricket-duleep-trophy-01",
            "title": "East Zone vs South Zone Duleep Trophy Thriller - Unstoppable Action",
            "summary": "East Zone battle South Zone in a high-voltage Duleep Trophy clash",
            "category": "cricket",
            "media_type": "REEL",
            "local_file": f"owned_reels/{v1.name}",
            "public_url": "https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/data/owned_reels/cricket_reel_east_vs_south_duleep_trophy_reel_916.mp4",
            "media_sha256": v1_sha,
            "rights_status": "OWNED",
            "rights_evidence": "Account-owned original cricket media asset",
            "license_url": "data/owned_reels/metadata.json",
            "commercial_use_allowed": True,
            "modification_allowed": True,
            "prepared_at": "2026-09-12T00:00:00+00:00"
        }
        with open(data_dir / "prepared_media.json", "w", encoding="utf-8") as f:
            json.dump(prep_data, f)

        with patch("instagram_media_verifier.InstagramMediaVerifier.validate_meta_media_accessibility") as mock_acc:
            mock_acc.return_value = {"is_valid": True}
            res = engine.publish_prepared()

        assert res.get("status") == "BLOCKED"
        assert "duplicate" in res.get("reason", "").lower() or "already published" in res.get("reason", "").lower()

    def test_E_duplicate_block_not_counted_as_meta_failure(self, tmp_path):
        """Test E: Verifies that duplicate safety block is tracked separately and not counted as a Meta publish failure."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        tracker = InstagramHealthTracker(health_path=str(data_dir / "instagram_health.json"))

        tracker.record_duplicate_block("Media URL already published.")

        health_data = tracker.get_health_summary()
        assert health_data.get("consecutive_publish_failures", 0) == 0
        assert health_data.get("production_paused", False) is False
        assert health_data.get("duplicate_blocks_count", 0) == 1

    def test_F_filename_normalization_prevents_duplicate_reel_916(self, tmp_path):
        """Test F: Verifies format_vertical_reel does not append duplicate _reel_916 suffix."""
        cfg = Config.load_from_env(validate=False)
        source = InstagramRealVideoSource(config=cfg)

        test_file = tmp_path / "cricket_reel_01_reel_916.mp4"
        test_file.write_bytes(b"dummy")

        formatted = source.format_vertical_reel(str(test_file))
        assert formatted == str(test_file)
        assert not formatted.endswith("_reel_916_reel_916.mp4")
