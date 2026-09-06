import os
import json
import pytest
from unittest.mock import MagicMock, patch
from config import Config
from instagram_real_video_source import InstagramRealVideoSource, OwnedVideoProvider
from instagram_source_verifier import InstagramSourceVerifier
from instagram_media_verifier import InstagramMediaVerifier
from instagram_final_publish_guard import InstagramFinalPublishGuard
from instagram_content_bundle import ContentBundle


def test_owned_media_with_valid_metadata(tmp_path):
    """Verifies OwnedVideoProvider acquires media when file and metadata.json are valid."""
    owned_dir = tmp_path / "owned_reels"
    owned_dir.mkdir()
    file_path = owned_dir / "test_reel.mp4"
    file_path.write_bytes(b"fake_mp4_bytes")

    meta_file = owned_dir / "metadata.json"
    meta_content = {
        "items": [
            {
                "file": "test_reel.mp4",
                "rights_status": "OWNED",
                "rights_evidence": "Account-owned media",
                "title": "Valid Owned Reel",
                "category": "cricket"
            }
        ]
    }
    meta_file.write_text(json.dumps(meta_content), encoding="utf-8")

    provider = OwnedVideoProvider(data_dir=str(tmp_path))
    items = provider.fetch_video_items(category="cricket")
    assert len(items) == 1
    assert items[0]["title"] == "Valid Owned Reel"
    assert items[0]["rights_status"] == "OWNED"
    assert items[0]["commercial_use_allowed"] is True


def test_owned_media_without_metadata(tmp_path):
    """Verifies OwnedVideoProvider rejects arbitrary files without explicit metadata entry."""
    owned_dir = tmp_path / "owned_reels"
    owned_dir.mkdir()
    file_path = owned_dir / "untracked_reel.mp4"
    file_path.write_bytes(b"fake_mp4_bytes")

    # No metadata.json exists
    provider = OwnedVideoProvider(data_dir=str(tmp_path))
    items = provider.fetch_video_items()
    assert len(items) == 0


def test_missing_rights_rejection():
    """Verifies candidate with missing rights status is rejected fail-closed."""
    config = Config.load_from_env(validate=False)
    guard = InstagramFinalPublishGuard(config=config)

    bundle = ContentBundle(
        content_id="test-no-rights",
        category="cricket",
        title="Public Video Without Rights",
        summary="Summary",
        source_url="https://example.com/video.html",
        source_domain="example.com",
        published_at="2026-09-06T00:00:00Z",
        media_url="https://example.com/video.mp4",
        media_type="REEL",
        media_rights_status="RIGHTS_EVIDENCE_MISSING",
    )
    res = guard.verify_and_guard(bundle)
    assert not res.is_valid
    assert res.error_code == "RIGHTS_EVIDENCE_MISSING"


def test_invalid_license_rejection():
    """Verifies candidate with non-allowed/invalid license is rejected."""
    config = Config.load_from_env(validate=False)
    guard = InstagramFinalPublishGuard(config=config)

    bundle = ContentBundle(
        content_id="test-invalid-license",
        category="cricket",
        title="Non Commercial Video",
        summary="Summary",
        source_url="https://example.com/video.html",
        source_domain="example.com",
        published_at="2026-09-06T00:00:00Z",
        media_url="https://example.com/video.mp4",
        media_type="REEL",
        media_rights_status="ALL_RIGHTS_RESERVED",
    )
    res = guard.verify_and_guard(bundle)
    assert not res.is_valid
    assert res.error_code == "RIGHTS_EVIDENCE_MISSING"


def test_explicit_authorization_evidence():
    """Verifies EXPLICITLY_AUTHORIZED status with valid evidence URL passes guard."""
    config = Config.load_from_env(validate=False)
    guard = InstagramFinalPublishGuard(config=config)

    bundle = ContentBundle(
        content_id="test-auth-01",
        category="cricket",
        title="Authorized Partner Video",
        summary="Summary",
        source_url="https://example.com/story",
        source_domain="example.com",
        published_at="2026-09-06T00:00:00Z",
        media_url="https://example.com/video.mp4",
        media_type="REEL",
        media_rights_status="EXPLICITLY_AUTHORIZED",
        caption="Authorized Partner Video",
    )
    bundle.rights_evidence_type = "EXPLICIT_WRITTEN_PERMIT"
    bundle.rights_evidence_url = "https://example.com/permission.pdf"

    res = guard.verify_and_guard(bundle)
    assert res.is_valid


def test_public_domain_evidence():
    """Verifies PUBLIC_DOMAIN status passes guard."""
    config = Config.load_from_env(validate=False)
    guard = InstagramFinalPublishGuard(config=config)

    bundle = ContentBundle(
        content_id="test-pd-01",
        category="cricket",
        title="Archive Match Footage",
        summary="Summary",
        source_url="https://archive.org/match",
        source_domain="archive.org",
        published_at="2026-09-06T00:00:00Z",
        media_url="https://archive.org/match.mp4",
        media_type="REEL",
        media_rights_status="PUBLIC_DOMAIN",
        caption="Archive Match Footage",
    )
    res = guard.verify_and_guard(bundle)
    assert res.is_valid


def test_cc_license_evidence():
    """Verifies VERIFIED_CC_LICENSE status passes guard."""
    config = Config.load_from_env(validate=False)
    guard = InstagramFinalPublishGuard(config=config)

    bundle = ContentBundle(
        content_id="test-cc-01",
        category="technology",
        title="Open Source Tech Demo",
        summary="Summary",
        source_url="https://example.com/tech",
        source_domain="example.com",
        published_at="2026-09-06T00:00:00Z",
        media_url="https://example.com/tech.mp4",
        media_type="REEL",
        media_rights_status="VERIFIED_CC_LICENSE",
        caption="Open Source Tech Demo",
    )
    res = guard.verify_and_guard(bundle)
    assert res.is_valid


def test_duplicate_owned_video(tmp_path):
    """Verifies duplicate owned video ID is rejected by guard."""
    config = Config.load_from_env(validate=False)
    guard = InstagramFinalPublishGuard(
        config=config,
        data_dir=str(tmp_path),
    )

    bundle = ContentBundle(
        content_id="dup-owned-id-01",
        category="cricket",
        title="Unique Cricket Title 123",
        summary="Summary",
        source_url="https://example.com/dup1",
        source_domain="example.com",
        published_at="2026-09-06T00:00:00Z",
        media_url="https://example.com/dup1.mp4",
        media_type="REEL",
        media_rights_status="OWNED",
        caption="Unique Cricket Title 123",
    )
    # Record item once
    guard.record_published_item(bundle, media_id="123456789")

    # Verify duplicate check blocks re-publishing
    res = guard.verify_and_guard(bundle)
    assert not res.is_valid
    assert "DUPLICATE" in res.error_code


def test_synthetic_test_video_rejection():
    """Verifies oceans.mp4, sample, and synthetic videos are barred in production mode."""
    config = Config.load_from_env(validate=False)
    guard = InstagramFinalPublishGuard(config=config)

    bundle = ContentBundle(
        content_id="test-synth-01",
        category="cricket",
        title="Fake Video Match",
        summary="Summary",
        source_url="https://example.com/fake",
        source_domain="example.com",
        published_at="2026-09-06T00:00:00Z",
        media_url="https://vjs.zencdn.net/v/oceans.mp4",
        media_type="REEL",
        media_rights_status="OWNED",
        caption="Fake Video Match",
    )
    res = guard.verify_and_guard(bundle)
    assert not res.is_valid
    assert res.error_code in ("INVALID_MEDIA", "DUPLICATE_MEDIA_URL", "NOT_REAL_VIDEO", "SYNTHETIC_ASSET")


def test_real_video_validation():
    """Verifies real video asset exists and has valid stream properties."""
    real_video_path = os.path.abspath("data/owned_reels/cricket_reel_01.mp4")
    assert os.path.exists(real_video_path)
    assert os.path.getsize(real_video_path) > 100000


def test_external_github_raw_validation():
    """Verifies GitHub Raw URL validation format."""
    from instagram_public_media_host import PublicMediaHost
    host = PublicMediaHost()
    url = host.get_public_url("data/owned_reels/cricket_reel_01.mp4")
    assert "raw.githubusercontent.com" in url
    assert url.endswith(".mp4")


def test_meta_verification_failure_handling():
    """Verifies Meta Graph API error fails closed without declaring verification success."""
    from main import live_production_verification
    with patch("instagram_client.InstagramAPIClient.get", side_effect=Exception("Meta API connection timeout")):
        success = live_production_verification()
        assert success is False


def test_successful_new_media_verification():
    """Verifies proof dictionary keys when verification succeeds."""
    from main import save_production_proof, get_production_proof
    proof_data = {
        "live_reel_verified": True,
        "status": "LIVE_REEL_VERIFIED",
        "instagram_media_id": "999888777666",
        "instagram_permalink": "https://www.instagram.com/p/999888777666/",
    }
    save_production_proof(proof_data)
    loaded = get_production_proof()
    assert loaded.get("live_reel_verified") is True
    assert loaded.get("instagram_media_id") == "999888777666"


def test_production_reel_discovery_disabled_gate():
    """Verifies live production verification fails closed if reel_discovery_enabled is False."""
    from main import live_production_verification
    with patch("config.Config.load_from_env") as mock_cfg:
        mock_instance = MagicMock()
        mock_instance.access_token = "valid_token"
        mock_instance.user_id = "valid_user_id"
        mock_instance.reel_discovery_enabled = False
        mock_cfg.return_value = mock_instance

        success = live_production_verification()
        assert success is False


def test_image_fallback_disabled_configuration():
    """Verifies 100% Reel target configuration settings."""
    config = Config.load_from_env(validate=False)
    assert getattr(config, "reel_discovery_enabled", True) is True
    assert getattr(config, "reel_first_enabled", True) is True
    assert config.reel_target_percent == 100
    assert config.image_target_percent == 0
    assert getattr(config, "image_fallback_enabled", False) is False
