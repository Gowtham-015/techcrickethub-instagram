import pytest
from unittest.mock import MagicMock, patch
from config import Config
from instagram_real_video_source import InstagramRealVideoSource


def test_discover_video_items_categories():
    cfg = Config.load_from_env(validate=False)
    source = InstagramRealVideoSource(config=cfg)

    categories = ["cricket", "technology", "geopolitics", "democracy", "entertainment"]
    for cat in categories:
        items = source.discover_video_items(category=cat, limit=2)
        assert len(items) > 0, f"Expected items for category {cat}"
        for item in items:
            assert item["category"] == cat, f"Item category '{item['category']}' does not match requested '{cat}'"
            assert "video_url" in item
            assert not item["video_url"].startswith("https://www.youtube.com/watch")
            assert not item["video_url"].startswith("https://youtu.be/")


def test_fallback_video_candidates_direct_mp4():
    cfg = Config.load_from_env(validate=False)
    source = InstagramRealVideoSource(config=cfg)
    items = source._get_fallback_real_video_candidates(category="geopolitics", limit=1)
    assert len(items) == 1
    assert items[0]["category"] == "geopolitics"
    assert items[0]["video_url"].endswith(".mp4")
