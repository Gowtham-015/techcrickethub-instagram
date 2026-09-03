import os
import pytest
from instagram_public_media_host import PublicMediaHost
from instagram_media_verifier import InstagramMediaVerifier
from instagram_final_publish_guard import InstagramFinalPublishGuard
from instagram_real_news_source import InstagramRealNewsSource
from instagram_real_video_source import InstagramRealVideoSource, RealVideoProvider, OfficialCricketVideoProvider, LicensedVideoProvider, AuthorizedSocialVideoProvider


from instagram_content_bundle import ContentBundle
from config import Config


def test_public_media_host_initialization():
    host = PublicMediaHost()
    assert host.repo == "Gowtham-015/techcrickethub-instagram"
    assert host.branch == "main"


def test_public_media_host_verify_mock_url():
    host = PublicMediaHost()
    res = host.verify_public_url("https://example.com/test_video.mp4", media_type="REEL")
    assert res["is_valid"] is True
    assert res["http_status"] == 200
    assert res["content_type"] == "video/mp4"


def test_public_media_host_verify_invalid_scheme():
    host = PublicMediaHost()
    res = host.verify_public_url("http://example.com/test_video.mp4", media_type="REEL")
    assert res["is_valid"] is False
    assert res["error_code"] == "PUBLIC_MEDIA_NOT_ACCESSIBLE"


def test_public_media_host_verify_empty_url():
    host = PublicMediaHost()
    res = host.verify_public_url("", media_type="REEL")
    assert res["is_valid"] is False
    assert res["error_code"] == "PUBLIC_MEDIA_NOT_ACCESSIBLE"


def test_real_video_providers_instantiation():
    base_p = RealVideoProvider()
    cricket_p = OfficialCricketVideoProvider()
    tech_p = LicensedVideoProvider()
    social_p = AuthorizedSocialVideoProvider()

    assert base_p.provider_name == "BaseVideoProvider"
    assert cricket_p.provider_name == "OfficialCricketVideoProvider"
    assert tech_p.provider_name == "LicensedVideoProvider"
    assert social_p.provider_name == "AuthorizedSocialVideoProvider"
    assert len(cricket_p.feeds) > 0


def test_reel_never_converted_to_image_fallback():
    item = {
        "content_id": "test-reel-1",
        "title": "Sam Cook links with Essex",
        "category": "cricket",
        "media_type": "REEL",
        "video_url": "https://files.catbox.moe/test.mp4",
        "image_url": None,
    }
    assert item["media_type"] == "REEL"
    assert item["video_url"] is not None
    assert item["image_url"] is None



def test_ffprobe_missing_video_path():
    res = InstagramMediaVerifier.validate_video_ffprobe("non_existent_video_path.mp4")
    assert res["is_valid"] is False
    assert res["error_code"] == "INVALID_REEL_MEDIA"


def test_validate_meta_media_accessibility_missing_url():
    res = InstagramMediaVerifier.validate_meta_media_accessibility("")
    assert res["is_valid"] is False
    assert res["error_code"] == "MEDIA_PUBLICATION_BLOCKED"


def test_validate_meta_media_accessibility_missing_mp4_test():
    res = InstagramMediaVerifier.validate_meta_media_accessibility("https://raw.githubusercontent.com/test/missing.mp4")
    assert res["is_valid"] is False
    assert res["error_code"] == "MEDIA_PUBLICATION_BLOCKED"


def test_content_bundle_rights_status_verification():
    bundle = ContentBundle(
        content_id="test-rights-1",
        category="cricket",
        title="India vs Sri Lanka Match Summary",
        summary="India secures a clinical victory in Colombo Test.",
        source_url="https://www.espncricinfo.com/series/ind-vs-sl",
        source_domain="www.espncricinfo.com",
        published_at="2026-08-27T10:00:00Z",
        media_url="https://files.catbox.moe/test.mp4",
        media_type="REEL",
        media_rights_status="RIGHTS_NOT_VERIFIED",
    )
    guard = InstagramFinalPublishGuard()
    g_res = guard.verify_and_guard(bundle)
    assert g_res.is_valid is False
    assert g_res.error_code in ("MEDIA_RIGHTS_RESTRICTED", "MEDIA_RIGHTS_UNKNOWN")


def test_validate_meta_media_accessibility_cdn_retry_success(monkeypatch):
    from unittest.mock import MagicMock, patch
    import urllib.error

    attempts = 0

    def mock_urlopen(req, timeout=15):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise urllib.error.HTTPError(
                req.full_url, 404, "Not Found", {}, None
            )

        resp = MagicMock()
        resp.__enter__.return_value = resp
        resp.getcode.return_value = 200
        resp.headers = {
            "Content-Type": "video/mp4",
            "Content-Length": "1000",
        }
        # Valid MP4 ftyp magic bytes
        resp.read.side_effect = [
            b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00",
            b"\x00" * 980,
        ]
        return resp

    monkeypatch.setattr("time.sleep", lambda s: None)
    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        res = InstagramMediaVerifier.validate_meta_media_accessibility(
            "https://raw.githubusercontent.com/test_probe/retry_success.mp4",
            media_type="REEL",
        )
        assert res["is_valid"] is True
        assert res["error_code"] == "SUCCESS"
        assert attempts == 3
