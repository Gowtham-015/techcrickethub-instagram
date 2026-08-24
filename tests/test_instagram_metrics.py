from instagram_analytics import InstagramAnalyticsEvent
from instagram_metrics import InstagramMetrics


def test_metrics_calculation():
    events = [
        InstagramAnalyticsEvent("1", "DISCOVERED", "c1", "", "cricket", "IMAGE"),
        InstagramAnalyticsEvent("2", "ACCEPTED", "c1", "", "cricket", "IMAGE"),
        InstagramAnalyticsEvent("3", "QUEUED", "c1", "", "cricket", "IMAGE"),
        InstagramAnalyticsEvent("4", "PUBLISHED", "c1", "", "cricket", "IMAGE"),
        InstagramAnalyticsEvent("5", "FAILED", "c2", "", "cricket", "IMAGE"),
    ]

    metrics = InstagramMetrics.calculate(events)
    assert metrics.total_discovered == 1
    assert metrics.total_published == 1
    assert metrics.total_failed == 1
    assert metrics.publish_success_rate == 50.0
    assert metrics.failure_rate == 50.0


def test_metrics_zero_division():
    metrics = InstagramMetrics.calculate([])
    assert metrics.publish_success_rate == 0.0
    assert metrics.failure_rate == 0.0
    assert metrics.duplicate_rate == 0.0
    assert metrics.rejection_rate == 0.0
