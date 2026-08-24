import pytest
from instagram_cricket_data_provider import CricketMatch
from instagram_cricket_match_intelligence import InstagramCricketMatchIntelligence


def test_match_intelligence_live_match_state():
    intel = InstagramCricketMatchIntelligence()
    mock_matches = [
        CricketMatch(
            match_id="m-1",
            series="IND vs SL Test",
            team_a="India",
            team_b="Sri Lanka",
            start_time="2026-08-25T10:00:00Z",
            status="LIVE",
            source="MockSource",
        )
    ]

    summary = intel.analyze_matches(mock_matches)
    assert summary.state == "LIVE_MATCH"
    assert summary.is_match_day is True
    assert summary.priority_multiplier == 2.0


def test_match_intelligence_no_match_state():
    intel = InstagramCricketMatchIntelligence()
    summary = intel.analyze_matches([])

    assert summary.state == "NO_MATCH"
    assert summary.is_match_day is False
    assert summary.priority_multiplier == 1.0
