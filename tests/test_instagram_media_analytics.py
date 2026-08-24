from instagram_analytics import InstagramAnalyticsEvent
from instagram_media_analytics import InstagramMediaAnalytics


def test_media_analytics_grouping():
    events = [
        InstagramAnalyticsEvent("1", "PUBLISHED", "c1", "", "cricket", "IMAGE", content_score=85),
        InstagramAnalyticsEvent("2", "PUBLISHED", "c2", "", "cricket", "REEL", content_score=75),
        InstagramAnalyticsEvent("3", "FAILED", "c3", "", "cricket", "REEL"),
    ]

    res = InstagramMediaAnalytics.analyze_media(events)

    assert res["IMAGE"]["published"] == 1
    assert res["IMAGE"]["success_rate"] == 100.0
    assert res["IMAGE"]["average_score"] == 85.0

    assert res["REEL"]["published"] == 1
    assert res["REEL"]["failed"] == 1
    assert res["REEL"]["success_rate"] == 50.0
