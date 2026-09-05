import pytest
from unittest.mock import MagicMock, patch
from config import Config
from instagram_real_video_source import InstagramRealVideoSource


def test_discover_video_items_categories():
    cfg = Config.load_from_env(validate=False)
    source = InstagramRealVideoSource(config=cfg)

    sample_rss = """<rss version="2.0">
        <channel>
            <title>Feed Title</title>
            <item>
                <title>Match Highlight Reel</title>
                <link>https://example.com/story</link>
                <description>Highlight reel summary</description>
                <enclosure url="https://example.com/video.mp4" type="video/mp4"/>
                <creativeCommons>https://creativecommons.org/licenses/by/4.0/</creativeCommons>
            </item>
        </channel>
    </rss>"""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = sample_rss

    categories = ["cricket", "technology", "geopolitics", "democracy", "entertainment"]
    with patch("requests.get", return_value=mock_resp):
        for cat in categories:
            items = source.discover_video_items(category=cat, limit=2)
            assert len(items) > 0, f"Expected items for category {cat}"
            for item in items:
                assert item["category"] == cat, f"Item category '{item['category']}' does not match requested '{cat}'"
                assert "video_url" in item


def test_fallback_video_candidates_direct_mp4():
    cfg = Config.load_from_env(validate=False)
    source = InstagramRealVideoSource(config=cfg)
    # Verify that synthetic/oceans.mp4 fallback candidate generation is completely purged
    assert not hasattr(source, "_get_fallback_real_video_candidates")
