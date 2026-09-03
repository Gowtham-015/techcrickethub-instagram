from instagram_trend_signals import InstagramTrendSignalProvider
from instagram_content_scorer import InstagramContentScorer
from instagram_pipeline import InstagramContent


def test_trend_signal_provider():
    provider = InstagramTrendSignalProvider()
    trends = provider.fetch_current_trends()
    assert "cricket" in trends or "ai" in trends or len(trends) > 0

    mult_match = provider.score_trend_relevance("ChatGPT Unveils New Quantum AI Feature", "OpenAI announces breakthrough")
    assert mult_match > 1.0

    mult_no_match = provider.score_trend_relevance("Unrelated Obscure Story Title XYZ")
    assert mult_no_match == 1.0


def test_content_scorer_trend_boost():
    provider = InstagramTrendSignalProvider()
    scorer = InstagramContentScorer(score_threshold=35, trend_provider=provider)

    content = InstagramContent(
        title="India vs Australia Test Match Cricket Wicket Highlights",
        summary="Watch the bowling spell and century celebrations in the Test match.",
        category="cricket",
        source="espncricinfo.com",
        caption="Cricket highlights #Cricket",
        image_url="https://example.com/photo.jpg",
        media_type="IMAGE",
    )

    res = scorer.score_content(content)
    assert "trend_boost" in res.breakdown
    assert res.total_score >= 35
