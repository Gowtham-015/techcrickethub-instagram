import pytest
from instagram_content_bundle import ContentBundle, ContentIntegrityValidator


def test_content_bundle_creation():
    bundle = ContentBundle(
        content_id="bundle-1",
        category="cricket",
        title="India vs Australia Test Match Update",
        summary="India leading by 150 runs in 2nd innings.",
        source_url="https://www.espncricinfo.com/match1",
        source_domain="espncricinfo.com",
        published_at="2026-08-25T00:00:00Z",
        media_url="https://images.unsplash.com/photo-1540747913346-19e32dc3e97e",
        media_type="IMAGE",
        caption="India vs Australia Test Match Update! #Cricket",
    )
    assert bundle.content_id == "bundle-1"
    assert bundle.category == "cricket"
    assert bundle.verification_status == "PENDING"

    h = bundle.calculate_media_hash()
    assert len(h) == 64  # SHA256 hex string


def test_content_integrity_validator_matched():
    validator = ContentIntegrityValidator()
    bundle = ContentBundle(
        content_id="bundle-matched",
        category="cricket",
        title="Jaiswal Scores Century in Colombo Test",
        summary="Yashasvi Jaiswal scored an outstanding 100.",
        source_url="https://www.espncricinfo.com/story123",
        source_domain="espncricinfo.com",
        published_at="2026-08-25T00:00:00Z",
        media_url="https://images.unsplash.com/photo-1540747913346-19e32dc3e97e",
        media_type="IMAGE",
        caption="Jaiswal Scores Century in Colombo Test! What a knock! #Cricket",
    )
    res = validator.validate_bundle(bundle)
    assert res.is_valid is True
    assert res.error_code == "SUCCESS"
    assert bundle.verification_status == "VERIFIED"


def test_content_integrity_validator_mismatched_caption():
    validator = ContentIntegrityValidator()
    bundle = ContentBundle(
        content_id="bundle-mismatched",
        category="cricket",
        title="Jaiswal Scores Century in Colombo Test",
        summary="Yashasvi Jaiswal scored 100.",
        source_url="https://www.espncricinfo.com/story123",
        source_domain="espncricinfo.com",
        published_at="2026-08-25T00:00:00Z",
        media_url="https://images.unsplash.com/photo-1540747913346-19e32dc3e97e",
        media_type="IMAGE",
        caption="Unrelated AI tech update about semiconductors and microchips.",
    )
    res = validator.validate_bundle(bundle)
    assert res.is_valid is False
    assert res.error_code == "CAPTION_MISMATCH"
