import os
import pytest
from instagram_content_bundle import ContentBundle
from instagram_final_publish_guard import InstagramFinalPublishGuard


def test_template_repetition_blocking(tmp_path):
    """Simulates 25 generated items from repeated content and asserts that identical graphic cards

    and content are rejected, resulting in 0 duplicate publications.
    """
    data_dir = str(tmp_path / "data")
    guard = InstagramFinalPublishGuard(data_dir=data_dir)

    # 1. First publish succeeds
    b_first = ContentBundle(
        content_id="item-repeat-01",
        category="technology",
        title="iCloud+ Hide My Email addresses will remain on icloud.com",
        summary="Apple clarifies email forwarding for iCloud users.",
        source_url="https://news.ycombinator.com/item?id=1001",
        source_domain="news.ycombinator.com",
        published_at="2026-08-25T00:00:00Z",
        media_url="https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/media/generated/card_01.jpg",
        media_type="IMAGE",
        caption="iCloud+ Hide My Email addresses will remain on icloud.com #TechNews",
    )

    res_first = guard.verify_and_guard(b_first)
    assert res_first.is_valid
    guard.record_published_item(bundle=b_first, media_id="media-repeat-01")

    # 2. Subsequent 24 attempts must all be rejected by Guard
    rejected_count = 0
    for i in range(2, 26):
        b_repeat = ContentBundle(
            content_id=f"item-repeat-{i:02d}",
            category="technology",
            title="iCloud+ Hide My Email addresses will remain on icloud.com",
            summary="Apple clarifies email forwarding for iCloud users.",
            source_url=f"https://news.ycombinator.com/item?id=1001&utm_source=feed_{i}",
            source_domain="news.ycombinator.com",
            published_at="2026-08-25T00:00:00Z",
            media_url="https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/media/generated/card_01.jpg",
            media_type="IMAGE",
            caption="iCloud+ Hide My Email addresses will remain on icloud.com #TechNews",
        )
        res = guard.verify_and_guard(b_repeat)
        if not res.is_valid:
            rejected_count += 1

    assert rejected_count == 24
