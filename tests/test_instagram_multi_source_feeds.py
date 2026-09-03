import os
import pytest
from config import Config
from instagram_real_news_source import InstagramRealNewsSource


def test_config_category_toggles():
    cfg = Config.load_from_env(validate=False)
    assert hasattr(cfg, "enable_cricket_category")
    assert hasattr(cfg, "enable_technology_category")
    assert hasattr(cfg, "enable_launches_category")
    assert hasattr(cfg, "enable_geopolitics_category")
    assert hasattr(cfg, "enable_democracy_category")
    assert hasattr(cfg, "enable_entertainment_category")
    assert cfg.enable_cricket_category is True


def test_real_news_source_multi_feed_lists():
    src = InstagramRealNewsSource()
    assert len(src.cricket_feeds) > 0
    assert len(src.tech_feeds) > 0
    assert len(src.launches_feeds) > 0
    assert len(src.geopolitics_feeds) > 0
    assert len(src.democracy_feeds) > 0
    assert len(src.entertainment_feeds) > 0


def test_category_toggle_disables_fetching(monkeypatch):
    cfg = Config.load_from_env(validate=False)
    cfg.enable_cricket_category = False
    cfg.enable_technology_category = True
    src = InstagramRealNewsSource(config=cfg)

    items = src.get_content_items()
    cricket_items = [i for i in items if i.get("category") == "cricket"]
    assert len(cricket_items) == 0
