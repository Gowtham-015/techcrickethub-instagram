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
    monkeypatch.setattr(InstagramRealNewsSource, "upload_to_public_host", lambda path, fallback: fallback)
    cfg = Config.load_from_env(validate=False)
    source = InstagramRealNewsSource(config=cfg)
    items = source.get_content_items()

    for item in items:
        assert not str(item.get("content_id", "")).startswith("sample-")
        assert item.get("source_name") is not None
        assert item.get("source_url") is not None
