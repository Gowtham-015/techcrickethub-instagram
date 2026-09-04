import pytest

from datetime import datetime, timezone, timedelta
from config import Config
from instagram_real_news_source import InstagramRealNewsSource


def test_real_news_source_stable_id_generation():
    id1 = InstagramRealNewsSource.generate_stable_id("https://example.com/article1", "espncricinfo.com")
    id2 = InstagramRealNewsSource.generate_stable_id("https://example.com/article1", "espncricinfo.com")
    id3 = InstagramRealNewsSource.generate_stable_id("https://example.com/article2", "espncricinfo.com")

    assert id1.startswith("real-")
    assert id1 == id2
    assert id1 != id3


def test_real_news_source_date_parsing():
    date_str = "Mon, 24 Aug 2026 15:30:00 GMT"
    parsed = InstagramRealNewsSource.parse_rss_date(date_str)

    assert isinstance(parsed, datetime)
    assert parsed.year == 2026
    assert parsed.month == 8
    assert parsed.day == 24


def test_real_news_source_sample_content_excluded(monkeypatch):
    sample_xml = """<rss version="2.0"><channel>
    <item><title>India vs Australia Test Cricket Update</title><link>https://espncricinfo.com/story/101</link><description>Great cricket match update.</description></item>
    </channel></rss>"""
    from unittest.mock import patch, MagicMock
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = sample_xml
    mock_resp.content = sample_xml.encode("utf-8")
    mock_reel_gen = MagicMock()
    mock_reel_gen.generate_reel_from_facts.return_value = {"success": True, "reel_path": "data/generated_reels/sample.mp4"}

    monkeypatch.setattr(InstagramRealNewsSource, "upload_to_public_host", lambda path, fallback: fallback)
    monkeypatch.setattr("instagram_real_video_source.InstagramRealVideoSource.discover_video_items", lambda self, category, limit: [])
    cfg = Config.load_from_env(validate=False)
    source = InstagramRealNewsSource(config=cfg)

    with patch("requests.get", return_value=mock_resp), patch("requests.post", return_value=mock_resp), patch("instagram_reel_generator.InstagramReelGenerator", return_value=mock_reel_gen):
        items = source.get_content_items()

    for item in items:
        assert not str(item.get("content_id", "")).startswith("sample-")
        assert item.get("source_name") is not None
        assert item.get("source_url") is not None


def test_upload_to_public_host_catbox_success(tmp_path):
    from unittest.mock import patch, MagicMock
    from instagram_public_media_host import PublicMediaHost

    test_file = tmp_path / "test_image.jpg"
    test_file.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 100)

    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200
    mock_post_resp.text = "https://files.catbox.moe/test_image.jpg\n"

    fallback_url = "https://raw.githubusercontent.com/foo/bar/main/test_image.jpg"

    with patch("requests.post", return_value=mock_post_resp):
        res = InstagramRealNewsSource.upload_to_public_host(str(test_file), fallback_url)
        assert res == "https://files.catbox.moe/test_image.jpg"

        host_res = PublicMediaHost().upload_video(str(test_file), fallback_raw_url=fallback_url)
        assert host_res == "https://files.catbox.moe/test_image.jpg"


