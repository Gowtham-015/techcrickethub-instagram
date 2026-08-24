from instagram_category_balancer import InstagramCategoryBalancer
from instagram_queue import InstagramQueueItem


def test_category_distribution():
    balancer = InstagramCategoryBalancer(max_category_percentage=40.0, window_size=5)

    items = [
        InstagramQueueItem(
            queue_id=f"q-{i}",
            content_id=f"c-{i}",
            media_type="IMAGE",
            title=f"Title {i}",
            media_url="https://example.com/img.jpg",
            caption="",
            category="cricket",
            scheduled_at="2026-08-24T20:00:00+00:00",
        )
        for i in range(3)
    ]
    items.append(
        InstagramQueueItem(
            queue_id="q-3",
            content_id="c-3",
            media_type="IMAGE",
            title="Tech Title",
            media_url="https://example.com/img2.jpg",
            caption="",
            category="technology",
            scheduled_at="2026-08-24T20:30:00+00:00",
        )
    )

    dist = balancer.calculate_distribution(items)
    assert dist["cricket"] == 75.0
    assert dist["technology"] == 25.0

    assert balancer.is_category_overrepresented("cricket", items) is True
    assert balancer.is_category_overrepresented("technology", items) is False
