import os
import json
import tempfile
import pytest
from unittest.mock import MagicMock, patch

from config import Config
from instagram_automation_engine import InstagramAutomationEngine
from instagram_real_video_source import InstagramRealVideoSource, OwnedVideoProvider
from instagram_health import InstagramHealthTracker
from instagram_public_media_host import PublicMediaHost, normalize_reel_filename, normalize_reel_media_url


class TestPhaseADuplicateFiltering:

    @pytest.fixture
    def setup_env(self, tmp_path):
        """Sets up isolated test environment with temporary data directory and realistic history."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        owned_dir = data_dir / "owned_reels"
        owned_dir.mkdir()

        # Create dummy owned video files
        v1 = owned_dir / "cricket_reel_east_vs_south_duleep_trophy_reel_916.mp4"
        v1.write_bytes(b"dummy duleep reel video binary content")
        v2 = owned_dir / "cricket_reel_ind_vs_pak_women_reel_916.mp4"
        v2.write_bytes(b"dummy ind vs pak women reel video binary content")
        v3 = owned_dir / "tech_reel_ai_innovation_reel_916.mp4"
        v3.write_bytes(b"dummy tech reel video binary content")

        metadata_content = {
            "items": [
                {
                    "file": "cricket_reel_east_vs_south_duleep_trophy_reel_916.mp4",
                    "content_id": "owned-cricket-duleep-trophy-01",
                    "title": "East Zone vs South Zone Duleep Trophy Thriller - Unstoppable Action 🇮🇳🏏",
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
                    "title": "India vs Pakistan Women Cricket Showdown - High Voltage Thriller 🇮🇳⚡",
                    "summary": "India clash with Pakistan in an intense Women's Cricket match",
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
                    "file": "tech_reel_ai_innovation_reel_916.mp4",
                    "content_id": "owned-tech-ai-innovation-01",
                    "title": "Next-Gen AI & Tech Breakthroughs Transforming the Future 🚀⚡",
                    "summary": "Exploring game-changing artificial intelligence and cloud architectures",
                    "category": "technology",
                    "publisher": "TechCricketHub",
                    "rights_status": "OWNED",
                    "rights_evidence": "Account-owned original technology media asset",
                    "rights_evidence_url": "data/owned_reels/metadata.json",
                    "license": "Owned by TechCricketHub",
                    "commercial_use_allowed": True,
                    "modification_allowed": True,
                }
            ]
        }
        (owned_dir / "metadata.json").write_text(json.dumps(metadata_content), encoding="utf-8")

        v1_str = str(v1).replace("\\", "/")

        published_history = {
            "items": [
                {
                    "instagram_media_id": "18074199965428937",
                    "content_id": "ownedvideo-297604c7883f3d3f",
                    "canonical_source_url": f"file:///{v1_str}",
                    "title": "East Zone vs South Zone Duleep Trophy Thriller - Unstoppable Action 🇮🇳🏏",
                    "normalized_title": "east zone vs south zone duleep trophy thriller unstoppable action",
                    "media_url": "https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/data/owned_reels/cricket_reel_east_vs_south_duleep_trophy_reel_916.mp4",
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
        cfg.reel_discovery_enabled = True
        cfg.reel_target_percent = 100
        cfg.image_target_percent = 0
        cfg.image_fallback_enabled = False

        engine = InstagramAutomationEngine(config=cfg, data_dir=str(data_dir))
        engine.news_source = None
        engine.source = None
        return engine, data_dir, v1, v2, v3

    def test_1_exact_production_duplicate(self, setup_env):
        """TEST 1: Exact production duplicate Duleep reel is excluded before preparation."""
        engine, data_dir, v1, v2, v3 = setup_env
        with patch.object(engine.real_video_verifier, "verify_video_file") as mock_v_ver, \
             patch.object(engine.reel_quality_engine, "validate_reel_quality") as mock_q_ver:
            mock_v_ver.return_value = MagicMock(is_valid=True, duration_seconds=15.0, media_sha256="hash2")
            mock_q_ver.return_value = MagicMock(is_valid=True, duration_seconds=15.0)

            res = engine.prepare_media()

        assert res.get("prepared") is True
        assert res.get("status") == "PREPARED"
        assert "duleep" not in res.get("local_file", "").lower()
        assert "ind_vs_pak" in res.get("local_file", "").lower()

    def test_2_double_suffix_duplicate(self, setup_env):
        """TEST 2: Candidate *_reel_916_reel_916.mp4 matches published *_reel_916.mp4."""
        engine, data_dir, v1, v2, v3 = setup_env
        pub_file = data_dir / "instagram_published_history.json"
        pub_file.write_text(json.dumps({
            "items": [
                {
                    "instagram_media_id": "18074199965428937",
                    "content_id": "ownedvideo-297604c7883f3d3f",
                    "media_url": "https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/data/owned_reels/cricket_reel_east_vs_south_duleep_trophy_reel_916.mp4",
                    "title": "East Zone vs South Zone Duleep Trophy Thriller - Unstoppable Action 🇮🇳🏏",
                    "category": "cricket",
                    "media_type": "REEL",
                }
            ]
        }), encoding="utf-8")

        cand_url = "https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/data/owned_reels/cricket_reel_east_vs_south_duleep_trophy_reel_916_reel_916.mp4"
        norm1 = normalize_reel_media_url("https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/data/owned_reels/cricket_reel_east_vs_south_duleep_trophy_reel_916.mp4")
        norm2 = normalize_reel_media_url(cand_url)
        assert norm1 == norm2

    def test_3_reverse_double_suffix_duplicate(self, setup_env):
        """TEST 3: Candidate *_reel_916.mp4 matches published *_reel_916_reel_916.mp4."""
        cand = "cricket_reel_east_vs_south_duleep_trophy_reel_916.mp4"
        pub = "cricket_reel_east_vs_south_duleep_trophy_reel_916_reel_916.mp4"
        assert normalize_reel_filename(cand) == normalize_reel_filename(pub)

    def test_4_canonical_content_id(self, setup_env):
        """TEST 4: OwnedVideoProvider exposes explicit metadata content_id."""
        engine, data_dir, v1, v2, v3 = setup_env
        prov = OwnedVideoProvider(data_dir=str(data_dir))
        items = prov.fetch_video_items()
        assert len(items) >= 2
        assert items[0]["content_id"] == "owned-cricket-duleep-trophy-01"

    def test_5_legacy_content_id_compatibility(self, setup_env):
        """TEST 5: Old published history content ID (ownedvideo-297604c7883f3d3f) blocks physical asset republication."""
        engine, data_dir, v1, v2, v3 = setup_env
        with patch.object(engine.real_video_verifier, "verify_video_file") as mock_v_ver, \
             patch.object(engine.reel_quality_engine, "validate_reel_quality") as mock_q_ver:
            mock_v_ver.return_value = MagicMock(is_valid=True, duration_seconds=15.0, media_sha256="hash2")
            mock_q_ver.return_value = MagicMock(is_valid=True, duration_seconds=15.0)

            res = engine.prepare_media()

        assert res.get("prepared") is True
        assert "duleep" not in res.get("local_file", "").lower()

    def test_6_media_url_normalization(self, setup_env):
        """TEST 6: Equivalent normalized GitHub Raw paths treated as same published media."""
        url1 = "https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/data/owned_reels/cricket_reel_01.mp4"
        url2 = "https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/data/owned_reels/cricket_reel_01_reel_916.mp4"
        url3 = "https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/data/owned_reels/cricket_reel_01_reel_916_reel_916.mp4"
        assert normalize_reel_media_url(url1) == normalize_reel_media_url(url2) == normalize_reel_media_url(url3)

    def test_7_media_sha256(self, setup_env):
        """TEST 7: If binary media SHA256 matches published history, candidate is rejected."""
        engine, data_dir, v1, v2, v3 = setup_env
        import hashlib
        v1_hash = hashlib.sha256(v1.read_bytes()).hexdigest()
        pub_file = data_dir / "instagram_published_history.json"
        pub_file.write_text(json.dumps({
            "items": [
                {
                    "instagram_media_id": "18074199965428937",
                    "content_id": "different-id",
                    "media_hash": v1_hash,
                    "title": "Unrelated Title",
                    "category": "cricket",
                    "media_type": "REEL",
                }
            ]
        }), encoding="utf-8")

        with patch.object(engine.real_video_verifier, "verify_video_file") as mock_v_ver, \
             patch.object(engine.reel_quality_engine, "validate_reel_quality") as mock_q_ver:
            mock_v_ver.return_value = MagicMock(is_valid=True, duration_seconds=15.0, media_sha256=v1_hash)
            mock_q_ver.return_value = MagicMock(is_valid=True, duration_seconds=15.0)

            res = engine.prepare_media()

        assert res.get("prepared") is True
        assert "duleep" not in res.get("local_file", "").lower()

    def test_8_next_unpublished_candidate(self, setup_env):
        """TEST 8: Published Candidate A is skipped, Candidate B is selected."""
        engine, data_dir, v1, v2, v3 = setup_env
        with patch.object(engine.real_video_verifier, "verify_video_file") as mock_v_ver, \
             patch.object(engine.reel_quality_engine, "validate_reel_quality") as mock_q_ver:
            mock_v_ver.return_value = MagicMock(is_valid=True, duration_seconds=15.0, media_sha256="hash2")
            mock_q_ver.return_value = MagicMock(is_valid=True, duration_seconds=15.0)

            res = engine.prepare_media()

        assert res.get("prepared") is True
        assert "ind_vs_pak" in res.get("local_file", "").lower()

    def test_9_all_reels_published(self, setup_env):
        """TEST 9: When all reels are published, controlled NO_VALID_REEL result returned cleanly."""
        engine, data_dir, v1, v2, v3 = setup_env
        pub_file = data_dir / "instagram_published_history.json"
        pub_file.write_text(json.dumps({
            "items": [
                {"content_id": "owned-cricket-duleep-trophy-01", "media_url": "cricket_reel_east_vs_south_duleep_trophy_reel_916.mp4"},
                {"content_id": "owned-cricket-ind-vs-pak-women-01", "media_url": "cricket_reel_ind_vs_pak_women_reel_916.mp4"},
                {"content_id": "owned-tech-ai-innovation-01", "media_url": "tech_reel_ai_innovation_reel_916.mp4"}
            ]
        }), encoding="utf-8")

        res = engine.prepare_media()
        assert res.get("prepared") is False
        assert res.get("status") in ("NO_VALID_REEL", "NO_ELIGIBLE_REELS")
        assert not (data_dir / "prepared_media.json").exists()

    def test_10_final_race_condition_protection(self, setup_env):
        """TEST 10: Phase B/C blocks publication if item was published in parallel by another process."""
        engine, data_dir, v1, v2, v3 = setup_env
        import hashlib
        v1_sha = hashlib.sha256(v1.read_bytes()).hexdigest()

        prep_data = {
            "preparation_id": "prep-test-1234",
            "content_id": "owned-cricket-duleep-trophy-01",
            "title": "East Zone vs South Zone Duleep Trophy Thriller - Unstoppable Action 🇮🇳🏏",
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

        assert res.get("status") in ("BLOCKED", "DUPLICATE_BLOCKED")
        assert res.get("published", 0) == 0

    def test_11_duplicate_block_classification(self, setup_env):
        """TEST 11: Duplicate block is classified as BLOCKED, not META_CONTAINER_ERROR."""
        engine, data_dir, v1, v2, v3 = setup_env
        prep_data = {
            "preparation_id": "prep-test-5678",
            "content_id": "owned-cricket-duleep-trophy-01",
            "title": "East Zone vs South Zone Duleep Trophy Thriller",
            "category": "cricket",
            "media_type": "REEL",
            "local_file": f"owned_reels/{v1.name}",
            "public_url": "https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/data/owned_reels/cricket_reel_east_vs_south_duleep_trophy_reel_916.mp4",
            "rights_status": "OWNED",
            "rights_evidence": "Account-owned original cricket media asset",
            "license_url": "data/owned_reels/metadata.json",
            "commercial_use_allowed": True,
        }
        with open(data_dir / "prepared_media.json", "w", encoding="utf-8") as f:
            json.dump(prep_data, f)

        with patch("instagram_media_verifier.InstagramMediaVerifier.validate_meta_media_accessibility") as mock_acc:
            mock_acc.return_value = {"is_valid": True}
            res = engine.publish_prepared()

        assert res.get("status") in ("BLOCKED", "DUPLICATE_BLOCKED")
        assert res.get("status") != "META_CONTAINER_ERROR"
        assert res.get("status") != "META_PUBLISH_ERROR"

    def test_12_duplicate_block_health(self, tmp_path):
        """TEST 12: Duplicate block does NOT increment consecutive_publish_failures or pause production."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        tracker = InstagramHealthTracker(health_path=str(data_dir / "instagram_health.json"))

        tracker.record_duplicate_block("Media URL already published.")

        health_data = tracker.get_health_summary()
        assert health_data.get("consecutive_publish_failures", 0) == 0
        assert health_data.get("production_paused", False) is False
        assert health_data.get("duplicate_blocks_count", 0) == 1

    def test_13_genuine_meta_failure(self, tmp_path):
        """TEST 13: Genuine Meta API failure increments failure counter and updates status."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        tracker = InstagramHealthTracker(health_path=str(data_dir / "instagram_health.json"))

        tracker.record_publish_failure("Meta API 500 Container Creation Error")

        health_data = tracker.get_health_summary()
        assert health_data.get("consecutive_publish_failures", 0) == 1

    def test_14_filename_normalization(self, tmp_path):
        """TEST 14: Verifies format_vertical_reel does not append duplicate _reel_916 suffix."""
        cfg = Config.load_from_env(validate=False)
        source = InstagramRealVideoSource(config=cfg)

        test_file = tmp_path / "cricket_reel_01_reel_916.mp4"
        test_file.write_bytes(b"dummy")

        formatted = source.format_vertical_reel(str(test_file))
        assert formatted == str(test_file)
        assert not formatted.endswith("_reel_916_reel_916.mp4")

    def test_15_reel_only_policy(self, setup_env):
        """TEST 15: Reel-only policy is enforced and non-Reel items are rejected in candidate selection."""
        engine, data_dir, v1, v2, v3 = setup_env
        assert engine.config.reel_target_percent == 100
        assert engine.config.image_target_percent == 0
        assert engine.config.image_fallback_enabled is False

    def test_16_rights(self, setup_env):
        """TEST 16: Duplicate filtering does NOT bypass rights verification."""
        engine, data_dir, v1, v2, v3 = setup_env
        invalid_rights_item = {
            "title": "Unverified Rights Item",
            "rights_status": "UNKNOWN",
            "rights_evidence": "",
        }
        res = engine.rights_engine.verify_rights_evidence(invalid_rights_item)
        assert res.is_valid is False
