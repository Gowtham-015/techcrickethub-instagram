from instagram_analytics import InstagramAnalyticsEvent
from instagram_category_analytics import InstagramCategoryAnalytics


def test_category_analytics_grouping():
    events = [
        InstagramAnalyticsEvent("1", "DISCOVERED", "c1", "", "cricket", "IMAGE"),
        InstagramAnalyticsEvent("2", "PUBLISHED", "c1", "", "cricket", "IMAGE", content_score=90),
        InstagramAnalyticsEvent("3", "DISCOVERED", "c2", "", "technology", "REEL"),
        InstagramAnalyticsEvent("4", "FAILED", "c2", "", "technology", "REEL"),
    ]

    res = InstagramCategoryAnalytics.analyze_categories(events)

    assert "cricket" in res
    assert res["cricket"]["total_content"] == 1
    assert res["cricket"]["published"] == 1
    assert res["cricket"]["success_rate"] == 100.0
    assert res["cricket"]["average_score"] == 90.0

    assert "technology" in res
    assert res["technology"]["failed"] == 1
    assert res["technology"]["success_rate"] == 0.0
