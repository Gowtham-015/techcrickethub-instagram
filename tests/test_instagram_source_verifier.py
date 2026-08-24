import pytest
from instagram_source_verifier import InstagramSourceVerifier, SourceVerificationResult


def test_source_verifier_valid_url():
    verifier = InstagramSourceVerifier()
    res = verifier.verify_source("https://i.ytimg.com/vi/pbYX4gp_5kE/maxresdefault.jpg")

    assert isinstance(res, SourceVerificationResult)
    assert res.is_valid is True
    assert res.status_code == 200


def test_source_verifier_missing_url():
    verifier = InstagramSourceVerifier()
    res = verifier.verify_source("")

    assert res.is_valid is False
    assert "Missing or empty source_url." in res.reasons[0]


def test_source_verifier_sample_content_rejection():
    verifier = InstagramSourceVerifier()
    item = {
        "content_id": "sample-001",
        "title": "Test Title",
        "source_url": "https://i.ytimg.com/vi/pbYX4gp_5kE/maxresdefault.jpg",
    }
    res = verifier.verify_item(item, strict_production=True)

    assert res.is_valid is False
    assert "sample-001" in res.reasons[0]
