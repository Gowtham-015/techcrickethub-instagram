import json
import pytest
from exceptions import InstagramError
from instagram_queue import InstagramQueue, InstagramQueueItem


@pytest.fixture
def queue_file(tmp_path):
    return str(tmp_path / "test_queue.json")


def test_queue_enqueue_and_get(queue_file):
    queue = InstagramQueue(queue_path=queue_file, max_queue_size=10)
    item = InstagramQueueItem(
        queue_id="q-1",
        content_id="c-1",
        media_type="IMAGE",
        title="Title",
        media_url="https://example.com/image.jpg",
        caption="Caption",
        category="cricket",
        scheduled_at="2026-08-24T20:00:00+00:00",
    )

    enqueued = queue.enqueue(item)
    assert enqueued.queue_id == "q-1"

    all_items = queue.get_all_items()
    assert len(all_items) == 1
    assert all_items[0].title == "Title"
    assert all_items[0].status == "PENDING"


def test_queue_duplicate_rejection(queue_file):
    queue = InstagramQueue(queue_path=queue_file, max_queue_size=10)
    item1 = InstagramQueueItem(
        queue_id="q-1",
        content_id="c-1",
        media_type="IMAGE",
        title="Title 1",
        media_url="https://example.com/image.jpg",
        caption="Caption 1",
        category="cricket",
        scheduled_at="2026-08-24T20:00:00+00:00",
    )
    queue.enqueue(item1)

    item2 = InstagramQueueItem(
        queue_id="q-2",
        content_id="c-1",  # duplicate content_id
        media_type="IMAGE",
        title="Title 2",
        media_url="https://example.com/other.jpg",
        caption="Caption 2",
        category="cricket",
        scheduled_at="2026-08-24T20:30:00+00:00",
    )

    with pytest.raises(InstagramError) as exc_info:
        queue.enqueue(item2)
    assert "Duplicate queue entry detected" in str(exc_info.value)


def test_queue_capacity_limit(queue_file):
    queue = InstagramQueue(queue_path=queue_file, max_queue_size=2)
    for i in range(2):
        item = InstagramQueueItem(
            queue_id=f"q-{i}",
            content_id=f"c-{i}",
            media_type="IMAGE",
            title=f"Title {i}",
            media_url=f"https://example.com/image_{i}.jpg",
            caption="Caption",
            category="cricket",
            scheduled_at="2026-08-24T20:00:00+00:00",
        )
        queue.enqueue(item)

    overflow_item = InstagramQueueItem(
        queue_id="q-overflow",
        content_id="c-overflow",
        media_type="IMAGE",
        title="Overflow Title",
        media_url="https://example.com/overflow.jpg",
        caption="Caption",
        category="cricket",
        scheduled_at="2026-08-24T20:00:00+00:00",
    )
    with pytest.raises(InstagramError) as exc_info:
        queue.enqueue(overflow_item)
    assert "Queue capacity limit reached" in str(exc_info.value)


def test_queue_status_transitions(queue_file):
    queue = InstagramQueue(queue_path=queue_file, max_queue_size=10)
    item = InstagramQueueItem(
        queue_id="q-1",
        content_id="c-1",
        media_type="IMAGE",
        title="Title",
        media_url="https://example.com/image.jpg",
        caption="Caption",
        category="cricket",
        scheduled_at="2026-08-24T20:00:00+00:00",
    )
    queue.enqueue(item)

    queue.mark_processing("q-1")
    items = queue.get_all_items()
    assert items[0].status == "PROCESSING"
    assert items[0].attempt_count == 1

    queue.mark_published("q-1", media_id="media_123", container_id="container_456")
    items = queue.get_all_items()
    assert items[0].status == "PUBLISHED"
    assert items[0].published_media_id == "media_123"
    assert items[0].created_media_container_id == "container_456"


def test_queue_retry_failed_items(queue_file):
    queue = InstagramQueue(queue_path=queue_file, max_queue_size=10)
    item = InstagramQueueItem(
        queue_id="q-1",
        content_id="c-1",
        media_type="IMAGE",
        title="Title",
        media_url="https://example.com/image.jpg",
        caption="Caption",
        category="cricket",
        scheduled_at="2026-08-24T20:00:00+00:00",
    )
    queue.enqueue(item)
    queue.mark_failed("q-1", error="Network timeout")

    items = queue.get_all_items()
    assert items[0].status == "FAILED"

    retried = queue.retry_failed(max_retries=3)
    assert len(retried) == 1
    items = queue.get_all_items()
    assert items[0].status == "PENDING"


def test_queue_corrupt_file_recovery(queue_file):
    with open(queue_file, "w", encoding="utf-8") as f:
        f.write("CORRUPTED_JSON_DATA{")

    queue = InstagramQueue(queue_path=queue_file)
    summary = queue.get_status_summary()
    assert summary["total"] == 0
