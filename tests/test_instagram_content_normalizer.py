import pytest
from exceptions import InstagramConfigError
from instagram_content_normalizer import InstagramContentNormalizer


def test_normalizer_valid_image_item():
    raw = {
        "id": "sample-101",
        "title": "  India   Wins Match  ",
        "summary": "  Full match details summary.  ",
        "category": "  CRICKET  ",
        "source": "  SportsDesk  ",
        "image_url": "https://example.com/image.jpg",
        "media_type": "image",
    }

    content = InstagramContentNormalizer.normalize(raw)

    assert content.title == "India Wins Match"
    assert content.summary == "Full match details summary."
    assert content.category == "cricket"
    assert content.source == "SportsDesk"
    assert content.image_url == "https://example.com/image.jpg"
    assert content.media_type == "IMAGE"
    assert content.metadata.get("content_id") == "sample-101"


def test_normalizer_valid_reel_item():
    raw = {
        "id": "sample-102",
        "title": "Autonomous Tech Clip",
        "summary": "High speed inference demo.",
        "category": "technology",
        "video_url": "https://example.com/video.mp4",
        "media_type": "reel",
    }

    content = InstagramContentNormalizer.normalize(raw)

    assert content.media_type == "REEL"
    assert content.video_url == "https://example.com/video.mp4"


def test_normalizer_missing_title_summary_and_caption():
    raw = {
        "id": "sample-103",
        "title": "   ",
        "summary": "",
        "image_url": "https://example.com/image.jpg",
    }
    with pytest.raises(InstagramConfigError) as exc_info:
        InstagramContentNormalizer.normalize(raw)
    assert "must contain a non-empty title, summary, or caption" in str(exc_info.value)


def test_normalizer_invalid_media_type():
    raw = {
        "title": "Title",
        "summary": "Summary",
        "image_url": "https://example.com/image.jpg",
        "media_type": "AUDIO",
    }
    with pytest.raises(InstagramConfigError) as exc_info:
        InstagramContentNormalizer.normalize(raw)
    assert "Invalid media_type" in str(exc_info.value)


def test_normalizer_missing_image_url_for_image_type():
    raw = {
        "title": "Title",
        "summary": "Summary",
        "media_type": "IMAGE",
        "image_url": "",
    }
    with pytest.raises(InstagramConfigError) as exc_info:
        InstagramContentNormalizer.normalize(raw)
    assert "IMAGE content type requires a valid image_url" in str(exc_info.value)


def test_normalizer_missing_video_url_for_reel_type():
    raw = {
        "title": "Title",
        "summary": "Summary",
        "media_type": "REEL",
        "video_url": "",
    }
    with pytest.raises(InstagramConfigError) as exc_info:
        InstagramContentNormalizer.normalize(raw)
    assert "REEL content type requires a valid video_url" in str(exc_info.value)
