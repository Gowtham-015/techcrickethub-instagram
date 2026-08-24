import os
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
import pytest

from config import Config
from instagram_pipeline import InstagramContentPipeline, PipelineResult
from instagram_queue import InstagramQueue, InstagramQueueItem
from instagram_scheduler import InstagramScheduler


@pytest.fixture
def scheduler_env(tmp_path):
    queue_file = str(tmp_path / "queue.json")
    lock_file = str(tmp_path / "scheduler.lock")
    queue = InstagramQueue(queue_path=queue_file)
    config = Config.load_from_env(validate=False)
    pipeline = MagicMock(spec=InstagramContentPipeline)
    pipeline.process_content.return_value = PipelineResult(
        success=True,
        dry_run=True,
        media_type="IMAGE",
        status="SKIPPED",
        message="Dry-run execution skipped",
    )

    scheduler = InstagramScheduler(
        queue=queue,
        pipeline=pipeline,
        config=config,
        lock_path=lock_file,
    )
    return scheduler, queue, pipeline, lock_file


def test_scheduler_lock_acquire_and_release(scheduler_env):
    scheduler, queue, pipeline, lock_file = scheduler_env

    assert scheduler.acquire_lock() is True
    assert os.path.exists(lock_file)

    assert scheduler.acquire_lock() is False

    scheduler.release_lock()
    assert not os.path.exists(lock_file)


def test_scheduler_stale_lock_recovery(scheduler_env):
    scheduler, queue, pipeline, lock_file = scheduler_env

    os.makedirs(os.path.dirname(lock_file), exist_ok=True)
    with open(lock_file, "w", encoding="utf-8") as f:
        f.write('{"pid": 99999, "timestamp": ' + str(time.time() - 400) + "}")

    assert scheduler.acquire_lock(stale_timeout_seconds=300) is True
    scheduler.release_lock()


def test_scheduler_due_item_detection(scheduler_env):
    scheduler, queue, pipeline, lock_file = scheduler_env

    past_time = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    future_time = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()

    due_item = InstagramQueueItem(
        queue_id="due-1",
        content_id="c-due",
        media_type="IMAGE",
        title="Due Title",
        media_url="https://example.com/image.jpg",
        caption="Caption",
        category="cricket",
        scheduled_at=past_time,
    )

    future_item = InstagramQueueItem(
        queue_id="future-1",
        content_id="c-future",
        media_type="IMAGE",
        title="Future Title",
        media_url="https://example.com/future.jpg",
        caption="Caption",
        category="cricket",
        scheduled_at=future_time,
    )

    assert scheduler.is_due(due_item) is True
    assert scheduler.is_due(future_item) is False


def test_scheduler_process_due_items_dry_run(scheduler_env):
    scheduler, queue, pipeline, lock_file = scheduler_env

    past_time = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    item = InstagramQueueItem(
        queue_id="q-due-1",
        content_id="c-due-1",
        media_type="IMAGE",
        title="Due Item",
        media_url="https://example.com/image.jpg",
        caption="Caption",
        category="cricket",
        scheduled_at=past_time,
    )
    queue.enqueue(item)

    results = scheduler.process_due_items()

    assert len(results) == 1
    assert results[0].success is True
    assert results[0].dry_run is True

    all_items = queue.get_all_items()
    assert all_items[0].status == "SKIPPED"
