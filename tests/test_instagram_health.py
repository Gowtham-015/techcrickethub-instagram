import json
import pytest
from instagram_health import InstagramHealthTracker


@pytest.fixture
def health_file(tmp_path):
    return str(tmp_path / "test_health.json")


def test_health_tracker_initialization(health_file):
    tracker = InstagramHealthTracker(health_path=health_file)
    summary = tracker.get_health_summary()

    assert summary["status"] == "STOPPED"
    assert summary["cycles_completed"] == 0
    assert summary["items_processed"] == 0


def test_health_tracker_set_status(health_file):
    tracker = InstagramHealthTracker(health_path=health_file)
    tracker.set_status("RUNNING")

    summary = tracker.get_health_summary()
    assert summary["status"] == "RUNNING"
    assert summary["started_at"] is not None
    assert summary["last_heartbeat"] is not None


def test_health_tracker_record_cycle(health_file):
    tracker = InstagramHealthTracker(health_path=health_file)
    tracker.set_status("RUNNING")
    tracker.record_cycle(processed=3, published=0, failed=0)

    summary = tracker.get_health_summary()
    assert summary["cycles_completed"] == 1
    assert summary["items_processed"] == 3
    assert summary["last_success_at"] is not None


def test_health_tracker_error_redaction(health_file):
    tracker = InstagramHealthTracker(health_path=health_file)
    secret_error = "API error with access_token=IGAAW7oCvAZBS1BZAFowdVRmMC1rOTZANS1VINkM2WUdTbjd2cHFXNUQxZAHBNOWp0UWZA5U3pvWXR6eThFNENzUmJuZA25LQ3YwZAWVSSnFDeHM0akhGbEVoQWdOZAzJWSUtjMkVtVlBMR3BBc1o2amJKTjJsS29Qb3NERGhqTGxGWGVOVQZDZD"
    tracker.record_cycle(error=secret_error)

    summary = tracker.get_health_summary()
    assert "[REDACTED]" in summary["last_error"]
    assert "IGAAW7o" not in summary["last_error"]


def test_health_tracker_corrupt_file_recovery(health_file):
    with open(health_file, "w", encoding="utf-8") as f:
        f.write("CORRUPTED_JSON")

    tracker = InstagramHealthTracker(health_path=health_file)
    summary = tracker.get_health_summary()
    assert summary["status"] == "STOPPED"
