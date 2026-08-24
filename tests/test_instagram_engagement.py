from instagram_engagement import LocalEngagementProvider


def test_local_engagement_provider_unavailable():
    provider = LocalEngagementProvider()
    metrics = provider.get_engagement_metrics("test_media_123")

    assert metrics["status"] == "ENGAGEMENT_DATA_UNAVAILABLE"
    assert metrics["likes"] is None
    assert metrics["comments"] is None
    assert "unavailable" in metrics["message"].lower()
