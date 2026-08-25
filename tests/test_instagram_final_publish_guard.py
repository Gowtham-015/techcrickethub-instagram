import os
import pytest
from instagram_content_bundle import ContentBundle
from instagram_final_publish_guard import InstagramFinalPublishGuard


@pytest.fixture
def temp_guard(tmp_path):
    data_dir = str(tmp_path / "data")
    return InstagramFinalPublishGuard(data_dir=data_dir)


def test_canonical_url_normalization(temp_guard):
    url1 = "https://example.com/article?utm_source=twitter&utm_medium=social"
    url2 = "https://example.com/article/"
    url3 = "https://www.example.com/article?fbclid=12345"

    c1 = temp_guard.canonicalize_url(url1)
    c2 = temp_guard.canonicalize_url(url2)
    c3 = temp_guard.canonicalize_url(url3)

    assert c1 == c2
    assert c1 == c3
    assert c1 == "https://example.com/article"


def test_fact_fingerprint_matching(temp_guard):
    f1 = temp_guard.calculate_fact_fingerprint("India Wins Match", "India beat Australia by 5 wickets.", ["India", "Australia"])
    f2 = temp_guard.calculate_fact_fingerprint("India Wins Match", "India beat Australia by 5 wickets.", ["India", "Australia"])
    f3 = temp_guard.calculate_fact_fingerprint("England Wins Match", "England beat Australia.", ["England"])

    assert f1 == f2
    assert f1 != f3


def test_duplicate_content_id_rejection(temp_guard):
    b1 = ContentBundle(
        content_id="item-100",
        category="cricket",
        title="Unique Story Title One",
        summary="Summary one",
        source_url="https://example.com/story-100",
        source_domain="example.com",
        published_at="2026-08-25T00:00:00Z",
        media_url="https://example.com/image1.jpg",
        media_type="IMAGE",
        caption="Unique Story Title One caption",
    )

    temp_guard.record_published_item(bundle=b1, media_id="media-100")

    # Second attempt with same content_id
    res = temp_guard.verify_and_guard(b1)
    assert not res.is_valid
    assert res.error_code == "DUPLICATE_SOURCE" or res.error_code == "DUPLICATE_CONTENT_ID"


def test_title_similarity_rejection(temp_guard):
    b1 = ContentBundle(
        content_id="item-201",
        category="cricket",
        title="India Defeats Australia in T20 Thriller Match",
        summary="India won by 4 runs.",
        source_url="https://example.com/story-201",
        source_domain="example.com",
        published_at="2026-08-25T00:00:00Z",
        media_url="https://example.com/image201.jpg",
        media_type="IMAGE",
        caption="India Defeats Australia in T20 Thriller Match #Cricket",
    )

    temp_guard.record_published_item(bundle=b1, media_id="media-201")

    # Similar title
    b2 = ContentBundle(
        content_id="item-202",
        category="cricket",
        title="India Defeats Australia in T20 Match Thriller",
        summary="India beat Australia in T20 match.",
        source_url="https://example.com/story-202",
        source_domain="example.com",
        published_at="2026-08-25T00:00:00Z",
        media_url="https://example.com/image202.jpg",
        media_type="IMAGE",
        caption="India Defeats Australia in T20 Match Thriller #Cricket",
    )

    res = temp_guard.verify_and_guard(b2)
    assert not res.is_valid
    assert res.error_code == "DUPLICATE_TITLE"


def test_caption_mismatch_rejection(temp_guard):
    b_mismatch = ContentBundle(
        content_id="item-301",
        category="cricket",
        title="India Announces T20 Squad for World Cup",
        summary="Selectores announce 15 player roster.",
        source_url="https://example.com/story-301",
        source_domain="example.com",
        published_at="2026-08-25T00:00:00Z",
        media_url="https://example.com/image301.jpg",
        media_type="IMAGE",
        caption="Unrelated commentary about quantum computing algorithms",
    )

    res = temp_guard.verify_and_guard(b_mismatch)
    assert not res.is_valid
    assert res.error_code == "CAPTION_MISMATCH"
