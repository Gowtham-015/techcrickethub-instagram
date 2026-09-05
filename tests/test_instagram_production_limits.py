import os
import pytest
from config import Config
from instagram_automation_engine import InstagramAutomationEngine
from instagram_health import InstagramHealthTracker
from instagram_production_gate import InstagramProductionGate
from instagram_scheduler import InstagramScheduler
from instagram_queue import InstagramQueue, InstagramQueueItem


def test_consecutive_failure_limit_pauses_production(tmp_path):
    health_file = str(tmp_path / "health.json")
    tracker = InstagramHealthTracker(health_path=health_file)

    max_failures = 3
    for i in range(max_failures):
        tracker.record_publish_failure(f"API Failure {i+1}", max_consecutive_failures=max_failures)

    summary = tracker.get_production_health_summary()
    assert summary["consecutive_publish_failures"] == 3
    assert summary["production_paused"] is True
    assert summary["pause_reason"] == "CONSECUTIVE_PUBLISH_FAILURES"
    assert summary["health_label"] == "PAUSED"


def test_production_reset_clears_pause_state(tmp_path):
    health_file = str(tmp_path / "health.json")
    tracker = InstagramHealthTracker(health_path=health_file)

    tracker.record_publish_failure("Fatal API Error", max_consecutive_failures=1)
    assert tracker.get_health_summary()["production_paused"] is True

    tracker.reset_production_state()
    summary = tracker.get_health_summary()
    assert summary["consecutive_publish_failures"] == 0
    assert summary["production_paused"] is False
    assert summary["pause_reason"] is None


def test_max_posts_per_cycle_limit(tmp_path):
    queue_file = str(tmp_path / "queue.json")
    queue = InstagramQueue(queue_path=queue_file)

    # Add 5 due items
    for i in range(5):
        queue.enqueue(
            InstagramQueueItem(
                queue_id=f"q-{i}",
                content_id=f"c-{i}",
                media_type="IMAGE",
                title=f"Test Item {i}",
                caption="Test Caption",
                category="cricket",
                media_url=f"https://example.com/image_{i}.jpg",
                scheduled_at="2020-01-01T00:00:00Z",
                status="PENDING",
            )
        )

    scheduler = InstagramScheduler(queue=queue, lock_path=str(tmp_path / "scheduler.lock"))
    results = scheduler.process_due_items(limit=1)
    assert len(results) == 1


def test_telegram_isolation_strict_check():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    py_files = [
        os.path.join(base_dir, f)
        for f in os.listdir(base_dir)
        if f.endswith(".py") and not f.startswith("test_")
    ]

    telegram_refs = []
    target_repo = "gowtham-015/" + "ai_news"
    for filepath in py_files:
        if os.path.basename(filepath) == "main.py":
            continue
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read().lower()
            if "import telegram" in content or "from telegram" in content or target_repo in content:
                telegram_refs.append(filepath)

    assert len(telegram_refs) == 0, f"Telegram references found in: {telegram_refs}"
