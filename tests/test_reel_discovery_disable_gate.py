import os
from unittest.mock import MagicMock, patch
import pytest

from config import Config
from instagram_real_video_source import InstagramRealVideoSource
from instagram_automation_engine import InstagramAutomationEngine
from instagram_public_media_host import PublicMediaHost


def test_reel_discovery_enabled_default_and_env_override(monkeypatch):
    monkeypatch.delenv("INSTAGRAM_REEL_DISCOVERY_ENABLED", raising=False)
    cfg_default = Config.load_from_env(env_path="", validate=False)
    assert cfg_default.reel_discovery_enabled is False

    monkeypatch.setenv("INSTAGRAM_REEL_DISCOVERY_ENABLED", "true")
    cfg_enabled = Config.load_from_env(env_path="", validate=False)
    assert cfg_enabled.reel_discovery_enabled is True

    monkeypatch.setenv("INSTAGRAM_REEL_DISCOVERY_ENABLED", "false")
    cfg_disabled = Config.load_from_env(env_path="", validate=False)
    assert cfg_disabled.reel_discovery_enabled is False


def test_video_source_returns_empty_when_disabled():
    cfg = Config.load_from_env(env_path="", validate=False)
    cfg.reel_discovery_enabled = False
    source = InstagramRealVideoSource(config=cfg)
    items = source.get_content_items()
    assert items == []


def test_engine_skips_video_discovery_when_disabled():
    cfg = Config.load_from_env(env_path="", validate=False)
    cfg.reel_discovery_enabled = False

    mock_video_source = MagicMock(spec=InstagramRealVideoSource)
    mock_news_source = MagicMock()
    mock_news_source.get_content_items.return_value = []

    engine = InstagramAutomationEngine(
        config=cfg,
        source=mock_video_source,
        news_source=mock_news_source,
    )

    engine.run_cycle()

    # Video source get_content_items should not have been called during engine cycle
    mock_video_source.get_content_items.assert_not_called()
    mock_news_source.get_content_items.assert_called_once()


def test_public_media_host_verification_cache(tmp_path):
    temp_file = tmp_path / "test_video.mp4"
    temp_file.write_bytes(b"mock mp4 content bytes")

    host = PublicMediaHost()
    host._VERIFICATION_CACHE.clear()

    fallback_url = "https://vjs.zencdn.net/v/oceans.mp4"

    with patch("instagram_media_verifier.InstagramMediaVerifier.validate_meta_media_accessibility") as mock_val:
        mock_val.return_value = {"is_valid": True, "http_status": 200}

        # First call should hit validate_meta_media_accessibility
        res1 = host.upload_video(str(temp_file), fallback_raw_url=fallback_url)
        assert res1 == fallback_url
        assert mock_val.call_count == 1

        # Second call with same fallback URL should use the cache
        res2 = host.upload_video(str(temp_file), fallback_raw_url=fallback_url)
        assert res2 == fallback_url
        assert mock_val.call_count == 1  # Still 1 because cache was hit!
