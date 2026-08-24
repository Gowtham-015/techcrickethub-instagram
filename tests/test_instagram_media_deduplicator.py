import os
from instagram_media_deduplicator import InstagramMediaDeduplicator


def test_deduplicator_new_content(tmp_path):
    history_path = tmp_path / "media_history.json"
    dedup = InstagramMediaDeduplicator(history_path=str(history_path))

    assert dedup.is_duplicate(content_id="sample-001", url="https://example.com/image.jpg") is False


def test_deduplicator_mark_and_detect_duplicate(tmp_path):
    history_path = tmp_path / "media_history.json"
    dedup = InstagramMediaDeduplicator(history_path=str(history_path))

    content_id = "sample-001"
    url = "https://example.com/image.jpg"

    dedup.mark_processed(content_id=content_id, url=url, status="SKIPPED")

    assert dedup.is_duplicate(content_id="sample-001") is True
    assert dedup.is_duplicate(url="https://example.com/image.jpg") is True
    assert dedup.is_duplicate(content_id="sample-999", url="https://example.com/other.jpg") is False


def test_deduplicator_corrupt_history_handling(tmp_path):
    history_path = tmp_path / "corrupt_history.json"
    history_path.write_text("INVALID_JSON_STATE{", encoding="utf-8")

    dedup = InstagramMediaDeduplicator(history_path=str(history_path))
    assert dedup.is_duplicate(content_id="sample-001") is False

    dedup.mark_processed(content_id="sample-001")
    assert dedup.is_duplicate(content_id="sample-001") is True
