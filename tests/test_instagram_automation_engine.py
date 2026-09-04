import os
import time
from unittest.mock import MagicMock
import pytest

from config import Config
from instagram_automation_engine import InstagramAutomationEngine
from instagram_content_source import InstagramContentSource
from instagram_health import InstagramHealthTracker
from instagram_media_acquirer import InstagramMediaAcquirer
from instagram_media_deduplicator import InstagramMediaDeduplicator
from instagram_queue import InstagramQueue
from instagram_scheduler import InstagramScheduler


@pytest.fixture
def engine_env(tmp_path):
    queue_file = str(tmp_path / "queue.json")
    lock_file = str(tmp_path / "engine.lock")
    health_file = str(tmp_path / "health.json")
    history_file = str(tmp_path / "history.json")

    config = Config.load_from_env(validate=False)
    config.dry_run = True
    queue = InstagramQueue(queue_path=queue_file)
    health = InstagramHealthTracker(health_path=health_file)
    source = MagicMock(spec=InstagramContentSource)
    source.get_content_items.return_value = [
        {
            "content_id": "test-eng-unique-101",
            "title": "Engine Test Title",
            "summary": "Engine test summary content",
            "category": "cricket",
            "media_type": "IMAGE",
            "image_url": "https://example.com/engine_test_image.jpg",
            "media_rights_status": "ORIGINAL_GENERATED",
        }
    ]
    scheduler = MagicMock(spec=InstagramScheduler)
    scheduler.process_due_items.return_value = []

    engine = InstagramAutomationEngine(
        config=config,
        source=source,
        queue=queue,
        scheduler=scheduler,
        health_tracker=health,
        lock_path=lock_file,
    )
    engine.deduplicator = InstagramMediaDeduplicator(history_path=history_file)
    engine.acquirer = MagicMock(spec=InstagramMediaAcquirer)
    return engine, queue, health, lock_file


def test_engine_lock_acquire_and_release(engine_env):
    engine, queue, health, lock_file = engine_env

    assert engine.acquire_lock() is True
    assert os.path.exists(lock_file)

    assert engine.acquire_lock() is False

    engine.release_lock()
    assert not os.path.exists(lock_file)


def test_engine_stale_lock_recovery(engine_env):
    engine, queue, health, lock_file = engine_env

    os.makedirs(os.path.dirname(lock_file), exist_ok=True)
    with open(lock_file, "w", encoding="utf-8") as f:
        f.write('{"pid": 99999, "timestamp": ' + str(time.time() - 400) + "}")

    assert engine.acquire_lock(stale_timeout_seconds=300) is True
    engine.release_lock()


def test_engine_run_cycle_dry_run(engine_env):
    engine, queue, health, lock_file = engine_env

    metrics = engine.run_cycle()

    assert metrics["discovered"] == 1
    assert metrics["valid"] == 1
    assert metrics["queued"] == 1
    assert metrics["dry_run"] is True

    health_summary = health.get_health_summary()
    assert health_summary["cycles_completed"] == 1
    assert health_summary["items_processed"] == 1


def test_engine_error_isolation(engine_env):
    engine, queue, health, lock_file = engine_env

    engine.source.get_content_items.return_value = [
        {"invalid": "no title or url"},
        {
            "content_id": "test-eng-valid-unique",
            "title": "Valid Item",
            "summary": "Valid summary",
            "category": "cricket",
            "media_type": "IMAGE",
            "image_url": "https://example.com/unique_valid_image_2.jpg",
            "media_rights_status": "ORIGINAL_GENERATED",
        },
    ]

    metrics = engine.run_cycle()

    assert metrics["discovered"] == 2
    assert metrics["failed"] >= 1


def test_intra_cycle_deduplication(engine_env):
    engine, queue, health, lock_file = engine_env

    duplicate_item_1 = {
        "content_id": "test-intra-cycle-dup-id",
        "title": "Duplicate Item First Instance",
        "summary": "First instance summary content",
        "category": "cricket",
        "media_type": "IMAGE",
        "image_url": "https://example.com/intra_cycle_image.jpg",
        "media_rights_status": "ORIGINAL_GENERATED",
    }

    duplicate_item_2 = {
        "content_id": "test-intra-cycle-dup-id",
        "title": "Duplicate Item Second Instance",
        "summary": "Second instance summary content",
        "category": "cricket",
        "media_type": "IMAGE",
        "image_url": "https://example.com/intra_cycle_image.jpg",
        "media_rights_status": "ORIGINAL_GENERATED",
    }

    engine.source.get_content_items.return_value = [duplicate_item_1, duplicate_item_2]

    metrics = engine.run_cycle()

    assert metrics["discovered"] == 2
    assert metrics["duplicates"] == 1
    assert metrics["queued"] == 1


def test_transient_failure_retried_on_next_cycle(engine_env):
    from unittest.mock import patch

    engine, queue, health, lock_file = engine_env

    transient_item = {
        "content_id": "test-transient-retry-id",
        "title": "Transient Failure Item",
        "summary": "Summary of item with transient failure",
        "category": "cricket",
        "media_type": "IMAGE",
        "image_url": "https://example.com/transient_image.jpg",
        "media_rights_status": "ORIGINAL_GENERATED",
    }

    engine.source.get_content_items.return_value = [transient_item]

    # Cycle 1: Simulate transient media verification failure (e.g. connection timeout)
    mock_transient_res = MagicMock(is_valid=False, error_code="HTTP_ERROR", message="Public media URL connection failed: Connection timed out")
    with patch.object(engine.media_verifier, "verify_and_deduplicate", return_value=mock_transient_res):
        metrics1 = engine.run_cycle()

    assert metrics1["discovered"] == 1
    assert metrics1["duplicates"] == 0
    assert metrics1["queued"] == 0

    # Cycle 2: Same item is provided again, media verification now succeeds
    mock_success_res = MagicMock(is_valid=True, message="Media OK", error_code="SUCCESS")
    with patch.object(engine.media_verifier, "verify_and_deduplicate", return_value=mock_success_res):
        metrics2 = engine.run_cycle()

    assert metrics2["discovered"] == 1
    assert metrics2["duplicates"] == 0
    assert metrics2["queued"] == 1


def test_permanent_failure_skipped_on_next_cycle(engine_env):
    engine, queue, health, lock_file = engine_env

    permanent_item = {
        "content_id": "test-permanent-fail-id",
        "title": "Permanent Failure Item",
        "summary": "Summary of item with permanent invalid source",
        "category": "cricket",
        "media_type": "IMAGE",
        "image_url": "https://example.com/permanent_image.jpg",
        "media_rights_status": "RIGHTS_NOT_VERIFIED",
    }

    engine.source.get_content_items.return_value = [permanent_item]

    # Cycle 1: Fails source verification (permanent failure)
    metrics1 = engine.run_cycle()
    assert metrics1["discovered"] == 1
    assert metrics1["failed"] == 1

    # Cycle 2: Same item presented on next cycle is caught as duplicate
    metrics2 = engine.run_cycle()
    assert metrics2["discovered"] == 1
    assert metrics2["duplicates"] == 1


