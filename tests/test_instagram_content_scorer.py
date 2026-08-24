from instagram_content_scorer import InstagramContentScorer
from instagram_pipeline import InstagramContent


def test_scorer_high_quality_content():
    scorer = InstagramContentScorer()
    content = InstagramContent(
        title="India Announces Roster Updates Ahead of Upcoming Tournament",
        summary="Key players return to training sessions following medical clearances prior to the upcoming international bilateral series.",
        category="cricket",
        source="SportsDesk",
        image_url="https://i.ytimg.com/vi/pbYX4gp_5kE/maxresdefault.jpg",
        media_type="IMAGE",
    )

    res = scorer.score_content(content)
    assert res.total_score >= 75
    assert res.decision == "ACCEPT"
    assert res.priority_label in ("HIGH", "CRITICAL")
    assert "title_quality" in res.breakdown


def test_scorer_low_quality_content():
    scorer = InstagramContentScorer(score_threshold=35)
    content = InstagramContent(
        title="Short",
        summary="",
        category="",
        image_url="",
        media_type="IMAGE",
    )

    res = scorer.score_content(content)
    assert res.total_score < 35
    assert res.decision == "REJECT"
    assert res.priority_label == "REJECT"
