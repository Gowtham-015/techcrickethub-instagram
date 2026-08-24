from instagram_analytics import InstagramAnalyticsEvent
from instagram_time_analytics import InstagramTimeAnalytics


def test_time_analytics_ist_windows():
    # 08:30 IST is Morning
    # 2026-08-24T03:00:00+00:00 UTC = 2026-08-24T08:30:00+05:30 IST
    events = [
        InstagramAnalyticsEvent(
            "1",
            "PUBLISHED",
            "c1",
            timestamp="2026-08-24T03:00:00+00:00",
            category="cricket",
            media_type="IMAGE",
        )
    ]

    res = InstagramTimeAnalytics.analyze_time_windows(events, tz_name="Asia/Kolkata")
    assert res["MORNING"]["published_count"] == 1
    assert res["MORNING"]["success_rate"] == 100.0
