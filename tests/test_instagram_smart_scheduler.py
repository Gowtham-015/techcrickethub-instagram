from datetime import datetime, timezone
from instagram_pipeline import InstagramContent
from instagram_queue import InstagramQueueItem
from instagram_smart_scheduler import InstagramSmartScheduler


def test_smart_scheduler_calculate_next_slot():
    scheduler = InstagramSmartScheduler()
    slot = scheduler.calculate_next_slot(queue_items=[], media_type="IMAGE")

    assert slot is not None
    assert slot.tzinfo is not None


def test_smart_scheduler_rank_candidates():
    scheduler = InstagramSmartScheduler()
    contents = [
        InstagramContent(
            title="Short Title",
            summary="",
            category="cricket",
            image_url="",
            media_type="IMAGE",
        ),
        InstagramContent(
            title="India Announces Roster Updates Ahead of Upcoming Tournament",
            summary="Key players return to training sessions following medical clearances prior to the upcoming international bilateral series.",
            category="cricket",
            source="SportsDesk",
            image_url="https://i.ytimg.com/vi/pbYX4gp_5kE/maxresdefault.jpg",
            media_type="IMAGE",
        ),
    ]

    ranked = scheduler.rank_candidates(contents, queue_items=[])
    assert len(ranked) >= 1
    best_content, best_score = ranked[0]
    assert best_score.total_score >= 75
