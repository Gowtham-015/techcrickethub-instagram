import pytest
from instagram_cricket_data_provider import (
    CricketMatch,
    CricAPICricketProvider,
    PublicRSSCricketProvider,
    FallbackCricketProvider,
)


def test_public_rss_cricket_provider():
    provider = PublicRSSCricketProvider()
    matches = provider.get_live_and_upcoming_matches()

    assert isinstance(matches, list)
    for m in matches:
        assert isinstance(m, CricketMatch)
        assert m.source == "ESPNCricinfo RSS"
        assert m.match_id.startswith("rss-cricket-")


def test_fallback_cricket_provider():
    provider = FallbackCricketProvider()
    matches = provider.get_live_and_upcoming_matches()

    assert isinstance(matches, list)
    for m in matches:
        assert isinstance(m, CricketMatch)
        assert m.source in ("CricAPI", "ESPNCricinfo RSS")


def test_cricapi_provider_without_key():
    provider = CricAPICricketProvider(api_key="")
    matches = provider.get_live_and_upcoming_matches()

    assert matches == []
