import os
import pytest
from instagram_content_bundle import ContentBundle
from instagram_final_duplicate_gate import InstagramFinalDuplicateGate


def test_final_duplicate_gate_url_canonicalization(tmp_path):
    gate = InstagramFinalDuplicateGate(data_dir=str(tmp_path))
    u1 = "https://www.espncricinfo.com/story/123?utm_source=rss&utm_medium=feed"
    u2 = "https://espncricinfo.com/story/123/"
    assert gate.canonicalize_url(u1) == gate.canonicalize_url(u2)


def test_final_duplicate_gate_text_normalization(tmp_path):
    gate = InstagramFinalDuplicateGate(data_dir=str(tmp_path))
    t1 = "India Wins Test Match against Australia in Sydney!!!"
    t2 = "india wins test match against australia in sydney"
    assert gate.normalize_text(t1) == gate.normalize_text(t2)


def test_final_duplicate_gate_rejection(tmp_path):
    gate = InstagramFinalDuplicateGate(data_dir=str(tmp_path))
    bundle1 = ContentBundle(
        content_id="bundle-001",
        category="cricket",
        title="Jaiswal Scores Historic Century",
        summary="Yashasvi Jaiswal scored 100 runs.",
        source_url="https://www.espncricinfo.com/story/jaiswal-100",
        source_domain="espncricinfo.com",
        published_at="2026-08-25T00:00:00Z",
        media_url="https://images.unsplash.com/photo-1540747913346-19e32dc3e97e",
        media_type="IMAGE",
        caption="Jaiswal Scores Historic Century! #Cricket",
    )

    # Initial check should pass
    res1 = gate.check_final_duplicate(bundle1)
    assert res1.is_valid is True
    assert res1.error_code == "SUCCESS"

    # Record publication
    gate.record_published_item(bundle1, media_id="1122334455")

    # Duplicate source URL check
    bundle_dup_url = ContentBundle(
        content_id="bundle-002",
        category="cricket",
        title="Different Title",
        summary="Summary",
        source_url="https://www.espncricinfo.com/story/jaiswal-100?utm_source=twitter",
        source_domain="espncricinfo.com",
        published_at="2026-08-25T00:00:00Z",
        media_url="https://images.unsplash.com/photo-100",
        media_type="IMAGE",
        caption="Different caption",
    )
    res_url = gate.check_final_duplicate(bundle_dup_url)
    assert res_url.is_valid is False
    assert res_url.error_code == "DUPLICATE_SOURCE"

    # Duplicate content ID check
    bundle_dup_id = ContentBundle(
        content_id="bundle-001",
        category="cricket",
        title="Different Title 2",
        summary="Summary",
        source_url="https://www.espncricinfo.com/story/different-101",
        source_domain="espncricinfo.com",
        published_at="2026-08-25T00:00:00Z",
        media_url="https://images.unsplash.com/photo-101",
        media_type="IMAGE",
        caption="Different caption 2",
    )
    res_id = gate.check_final_duplicate(bundle_dup_id)
    assert res_id.is_valid is False
    assert res_id.error_code == "DUPLICATE_CONTENT_ID"

    # Near-duplicate title check
    bundle_dup_title = ContentBundle(
        content_id="bundle-003",
        category="cricket",
        title="Jaiswal Scores Historic 100 Runs Century",
        summary="Summary",
        source_url="https://www.espncricinfo.com/story/different-102",
        source_domain="espncricinfo.com",
        published_at="2026-08-25T00:00:00Z",
        media_url="https://images.unsplash.com/photo-102",
        media_type="IMAGE",
        caption="Different caption 3",
    )
    res_title = gate.check_final_duplicate(bundle_dup_title)
    assert res_title.is_valid is False
    assert res_title.error_code == "DUPLICATE_TITLE"
