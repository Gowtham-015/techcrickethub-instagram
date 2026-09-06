import json
import os
import pytest
import shutil
import tempfile
from config import Config
from instagram_content_bundle import ContentBundle
from instagram_final_publish_guard import InstagramFinalPublishGuard
from instagram_automation_engine import InstagramAutomationEngine
from instagram_real_video_source import OwnedVideoProvider, InstagramRealVideoSource


def test_workflow_has_no_failure_masking():
    """Verify GitHub Actions workflow YAML contains no || echo or || true in production commands."""
    wf_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".github", "workflows", "instagram-publisher.yml")
    assert os.path.exists(wf_path)
    with open(wf_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Verify python-version is 3.11
    assert "python-version: '3.11'" in content
    # Verify cron schedule '7,27,47 * * * *'
    assert "- cron: '7,27,47 * * * *'" in content
    # Verify no failure masking in python commands
    assert "python main.py --prepare-media ||" not in content
    assert "python main.py --publish-prepared ||" not in content
    assert "python main.py --production-diagnostics ||" not in content


def test_windows_path_contamination_rejected(tmp_path):
    """Verify prepare_media metadata rejects Windows absolute drive letter paths."""
    config = Config.load_from_env(validate=False)
    data_dir = str(tmp_path / "data")
    os.makedirs(data_dir, exist_ok=True)
    engine = InstagramAutomationEngine(config=config, data_dir=data_dir)

    prep_file = os.path.join(data_dir, "prepared_media.json")
    stale_data = {
        "preparation_id": "prep-12345-test",
        "content_id": "test-win-path",
        "local_file": "D:\\instagram agent\\data\\owned_reels\\test.mp4",
        "public_url": "https://raw.githubusercontent.com/test.mp4",
        "media_type": "REEL",
    }
    with open(prep_file, "w", encoding="utf-8") as f:
        json.dump(stale_data, f)

    res = engine.publish_prepared()
    assert res["status"] == "FAILED"
    assert "Windows absolute path contamination" in res["reason"]


def test_stale_github_run_id_rejected(tmp_path):
    """Verify prepared media created in an older GITHUB_RUN_ID is rejected."""
    config = Config.load_from_env(validate=False)
    data_dir = str(tmp_path / "data")
    os.makedirs(data_dir, exist_ok=True)
    engine = InstagramAutomationEngine(config=config, data_dir=data_dir)

    prep_file = os.path.join(data_dir, "prepared_media.json")
    stale_data = {
        "preparation_id": "prep-12345-test",
        "content_id": "test-stale-run",
        "local_file": "data/owned_reels/cricket_reel_01_reel_916.mp4",
        "public_url": "https://raw.githubusercontent.com/test.mp4",
        "media_type": "REEL",
        "github_run_id": "99999999",
    }
    with open(prep_file, "w", encoding="utf-8") as f:
        json.dump(stale_data, f)

    os.environ["GITHUB_RUN_ID"] = "11111111"
    try:
        res = engine.publish_prepared()
        assert res["status"] == "FAILED"
        assert "Stale GitHub run ID" in res["reason"]
    finally:
        os.environ.pop("GITHUB_RUN_ID", None)


def test_missing_commercial_rights_rejected(tmp_path):
    """Verify media items with commercial_use_allowed=False are rejected by final publish guard."""
    config = Config.load_from_env(validate=False)
    guard = InstagramFinalPublishGuard(config=config, data_dir=str(tmp_path))

    bundle = ContentBundle(
        content_id="no-comm-001",
        category="cricket",
        title="Non-commercial Title",
        summary="Summary",
        source_url="https://example.com/noncomm",
        source_domain="example.com",
        published_at="2026-09-06T00:00:00Z",
        media_url="https://example.com/noncomm.mp4",
        media_type="REEL",
        media_rights_status="OWNED",
        commercial_use_allowed=False,
    )
    res = guard.verify_and_guard(bundle)
    assert not res.is_valid
    assert res.error_code == "LICENSE_NOT_COMMERCIAL"


def test_authorized_without_evidence_rejected(tmp_path):
    """Verify AUTHORIZED or CC_LICENSE_ALLOWED status without explicit evidence URLs are rejected."""
    config = Config.load_from_env(validate=False)
    guard = InstagramFinalPublishGuard(config=config, data_dir=str(tmp_path))

    b1 = ContentBundle(
        content_id="auth-001",
        category="cricket",
        title="Generic Authorized Title",
        summary="Summary",
        source_url="https://example.com/auth1",
        source_domain="example.com",
        published_at="2026-09-06T00:00:00Z",
        media_url="https://example.com/auth1.mp4",
        media_type="REEL",
        media_rights_status="AUTHORIZED",
    )
    res1 = guard.verify_and_guard(b1)
    assert not res1.is_valid
    assert res1.error_code == "RIGHTS_EVIDENCE_MISSING"

    b2 = ContentBundle(
        content_id="cc-001",
        category="cricket",
        title="Generic CC Title",
        summary="Summary",
        source_url="https://example.com/cc1",
        source_domain="example.com",
        published_at="2026-09-06T00:00:00Z",
        media_url="https://example.com/cc1.mp4",
        media_type="REEL",
        media_rights_status="CC_LICENSE_ALLOWED",
    )
    res2 = guard.verify_and_guard(b2)
    assert not res2.is_valid
    assert res2.error_code == "RIGHTS_EVIDENCE_MISSING"


def test_owned_media_requires_metadata(tmp_path):
    """Verify OwnedVideoProvider returns empty list if metadata.json is missing."""
    empty_dir = str(tmp_path / "empty_owned")
    os.makedirs(empty_dir, exist_ok=True)
    provider = OwnedVideoProvider(data_dir=empty_dir)
    items = provider.fetch_video_items()
    assert items == []


def test_reel_only_production_configuration():
    """Verify production configuration enforces 100% Reel target and disabled image fallback."""
    config = Config.load_from_env(validate=False)
    assert config.reel_discovery_enabled is True
    assert config.reel_target_percent == 100
    assert config.image_target_percent == 0
    assert config.enable_image_fallback is False
