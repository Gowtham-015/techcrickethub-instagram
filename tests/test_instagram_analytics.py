import os
import tempfile
from instagram_analytics import InstagramAnalyticsEvent, InstagramAnalyticsStore


def test_analytics_event_secret_redaction():
    event = InstagramAnalyticsEvent(
        event_id="e-101",
        event_type="FAILED",
        content_id="c-101",
        timestamp="",
        category="cricket",
        media_type="IMAGE",
        error="API error with access_token=IGAAW7oCvAZBS1BZAFowdVRmMC1rOTZANS1VINkM2WUdTbjd2cHFXNUQxZAHBNOWp0UWZA5U3pvWXR6eThFNENzUmJuZA25LQ3YwZAWVSSnFDeHM0akhGbEVoQWdOZAzJWSUtjMkVtVlBMR3BBc1o2amJKTjJsS29Qb3NERGhqTGxGWGVOVQZDZD",
    )
    d = event.to_dict()
    assert "[REDACTED]" in d["error"]
    assert "IGAAW7oCvAZBS1BZAFowdVRmMC1rOTZANS1VINkM2WUdTbjd2cHFXNUQxZAHBNOWp0UWZA5U3pvWXR6eThFNENzUmJuZA25LQ3YwZAWVSSnFDeHM0akhGbEVoQWdOZAzJWSUtjMkVtVlBMR3BBc1o2amJKTjJsS29Qb3NERGhqTGxGWGVOVQZDZD" not in d["error"]


def test_analytics_store_persistence_and_recovery():
    with tempfile.TemporaryDirectory() as tmpdir:
        store_file = os.path.join(tmpdir, "test_analytics.json")
        store = InstagramAnalyticsStore(analytics_path=store_file)

        e = InstagramAnalyticsEvent(
            event_id="e-001",
            event_type="PUBLISHED",
            content_id="c-001",
            timestamp="",
            category="technology",
            media_type="IMAGE",
        )
        store.record_event(e)

        events = store.get_events()
        assert len(events) == 1
        assert events[0].event_id == "e-001"
        assert events[0].category == "technology"

        # Corrupt file test
        with open(store_file, "w", encoding="utf-8") as f:
            f.write("corrupted json")

        store2 = InstagramAnalyticsStore(analytics_path=store_file)
        events2 = store2.get_events()
        assert len(events2) == 0
