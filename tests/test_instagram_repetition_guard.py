from instagram_pipeline import InstagramContent
from instagram_queue import InstagramQueueItem
from instagram_repetition_guard import InstagramRepetitionGuard


def test_repetition_guard_exact_media_url():
    guard = InstagramRepetitionGuard()
    content = InstagramContent(
        title="Unique Title",
        summary="Summary",
        category="cricket",
        image_url="https://example.com/shared_image.jpg",
        media_type="IMAGE",
    )

    existing = [
        InstagramQueueItem(
            queue_id="q-1",
            content_id="c-1",
            media_type="IMAGE",
            title="Different Title",
            media_url="https://example.com/shared_image.jpg",
            caption="",
            category="cricket",
            scheduled_at="2026-08-24T20:00:00+00:00",
        )
    ]

    res = guard.check_repetition(content, existing)
    assert res.is_repeated is True
    assert res.repetition_type == "EXACT_DUPLICATE"


def test_repetition_guard_near_duplicate_title():
    guard = InstagramRepetitionGuard(near_duplicate_threshold=0.85)
    content = InstagramContent(
        title="India Announces Squad Roster Updates Ahead of Big Tournament",
        summary="Summary",
        category="cricket",
        image_url="https://example.com/img1.jpg",
        media_type="IMAGE",
    )

    existing = [
        InstagramQueueItem(
            queue_id="q-1",
            content_id="c-1",
            media_type="IMAGE",
            title="India Announces Key Player Roster Updates Ahead of Big Tournament",
            media_url="https://example.com/img2.jpg",
            caption="",
            category="cricket",
            scheduled_at="2026-08-24T20:00:00+00:00",
        )
    ]

    res = guard.check_repetition(content, existing)
    assert res.is_repeated is True
    assert res.repetition_type == "NEAR_DUPLICATE"
    assert 0.85 <= res.similarity_score < 0.99
