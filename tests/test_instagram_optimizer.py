from config import Config
from instagram_analytics import InstagramAnalyticsEvent
from instagram_optimizer import InstagramOptimizer


def test_optimizer_insufficient_sample_size():
    cfg = Config.load_from_env(validate=False)
    cfg.analytics_min_sample_size = 10

    optimizer = InstagramOptimizer(config=cfg)
    rec = optimizer.generate_recommendations([])

    assert rec.confidence_status == "INSUFFICIENT_DATA"
    assert "INSUFFICIENT_DATA" in rec.category_recommendation


def test_optimizer_sufficient_sample_size():
    cfg = Config.load_from_env(validate=False)
    cfg.analytics_min_sample_size = 5

    events = [
        InstagramAnalyticsEvent(f"e-{i}", "PUBLISHED", f"c-{i}", "2026-08-24T03:00:00+00:00", "cricket", "IMAGE")
        for i in range(6)
    ]

    optimizer = InstagramOptimizer(config=cfg)
    rec = optimizer.generate_recommendations(events)

    assert rec.confidence_status == "SUFFICIENT"
    assert "cricket" in rec.category_recommendation.lower()
