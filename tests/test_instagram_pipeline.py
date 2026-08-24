from unittest.mock import MagicMock
import pytest

from exceptions import InstagramAPIError, InstagramConnectionError, InstagramError, InstagramTimeoutError
from instagram_pipeline import InstagramContent, InstagramContentPipeline, PipelineResult
from instagram_publisher import InstagramImagePublisher, PublishResult as ImagePublishResult
from instagram_reel_publisher import InstagramReelPublisher, PublishResult as ReelPublishResult


@pytest.fixture
def mock_image_publisher():
    pub = MagicMock(spec=InstagramImagePublisher)
    pub.client = MagicMock(access_token="MOCK_ACCESS_TOKEN_123")
    pub.validate_image_url.return_value = None
    pub.publish_image.return_value = ImagePublishResult(
        success=True,
        creation_id="17900000000000001",
        media_id="17900000000000002",
        message="Image published successfully",
    )
    return pub


@pytest.fixture
def mock_reel_publisher():
    pub = MagicMock(spec=InstagramReelPublisher)
    pub.client = MagicMock(access_token="MOCK_ACCESS_TOKEN_123")
    pub.validate_video_url.return_value = None
    pub.publish_reel.return_value = ReelPublishResult(
        success=True,
        creation_id="18000000000000001",
        media_id="18000000000000002",
        status="PUBLISHED",
        message="Reel published successfully",
    )
    return pub


def test_dry_run_image_pipeline(mock_image_publisher, mock_reel_publisher):
    pipeline = InstagramContentPipeline(
        image_publisher=mock_image_publisher,
        reel_publisher=mock_reel_publisher,
        dry_run=True,
    )

    content = InstagramContent(
        title="Cricket Tournament Final Update",
        summary="Team secures impressive victory in the closing match of the season.",
        category="cricket",
        image_url="https://example.com/image.jpg",
        media_type="IMAGE",
    )

    result = pipeline.process_content(content)

    assert result.success is True
    assert result.dry_run is True
    assert result.media_type == "IMAGE"
    assert result.status == "SKIPPED"
    assert "Publishing skipped" in result.message
    assert "#TechCricketHub" in result.caption
    assert mock_image_publisher.publish_image.call_count == 0


def test_dry_run_reel_pipeline(mock_image_publisher, mock_reel_publisher):
    pipeline = InstagramContentPipeline(
        image_publisher=mock_image_publisher,
        reel_publisher=mock_reel_publisher,
        dry_run=True,
    )

    content = InstagramContent(
        title="Highlight Reel Video",
        summary="Match highlights clip showcasing top bowling wickets.",
        category="cricket",
        video_url="https://example.com/video.mp4",
        media_type="REEL",
    )

    result = pipeline.process_content(content)

    assert result.success is True
    assert result.dry_run is True
    assert result.media_type == "REEL"
    assert result.status == "SKIPPED"
    assert mock_reel_publisher.publish_reel.call_count == 0


def test_real_publishing_image_pipeline(mock_image_publisher, mock_reel_publisher):
    pipeline = InstagramContentPipeline(
        image_publisher=mock_image_publisher,
        reel_publisher=mock_reel_publisher,
        dry_run=False,
    )

    content = InstagramContent(
        title="Tech Update Post",
        summary="New AI model benchmarks released.",
        category="technology",
        image_url="https://example.com/image.jpg",
        media_type="IMAGE",
    )

    result = pipeline.process_content(content)

    assert result.success is True
    assert result.dry_run is False
    assert result.creation_id == "17900000000000001"
    assert result.media_id == "17900000000000002"
    assert result.status == "PUBLISHED"
    mock_image_publisher.publish_image.assert_called_once()


def test_real_publishing_reel_pipeline(mock_image_publisher, mock_reel_publisher):
    pipeline = InstagramContentPipeline(
        image_publisher=mock_image_publisher,
        reel_publisher=mock_reel_publisher,
        dry_run=False,
    )

    content = InstagramContent(
        title="Reel Video Test",
        summary="Summary for reel video.",
        category="sports",
        video_url="https://example.com/video.mp4",
        media_type="REEL",
    )

    result = pipeline.process_content(content)

    assert result.success is True
    assert result.dry_run is False
    assert result.creation_id == "18000000000000001"
    assert result.media_id == "18000000000000002"
    assert result.status == "PUBLISHED"
    mock_reel_publisher.publish_reel.assert_called_once()


def test_missing_image_url(mock_image_publisher, mock_reel_publisher):
    pipeline = InstagramContentPipeline(
        image_publisher=mock_image_publisher,
        reel_publisher=mock_reel_publisher,
        dry_run=True,
    )

    content = InstagramContent(
        title="Headline",
        summary="Summary text",
        media_type="IMAGE",
        image_url="",
    )

    result = pipeline.process_content(content)
    assert result.success is False
    assert "requires a non-empty image_url" in result.message


def test_missing_video_url(mock_image_publisher, mock_reel_publisher):
    pipeline = InstagramContentPipeline(
        image_publisher=mock_image_publisher,
        reel_publisher=mock_reel_publisher,
        dry_run=True,
    )

    content = InstagramContent(
        title="Headline",
        summary="Summary text",
        media_type="REEL",
        video_url="",
    )

    result = pipeline.process_content(content)
    assert result.success is False
    assert "requires a non-empty video_url" in result.message


def test_unsupported_media_type(mock_image_publisher, mock_reel_publisher):
    pipeline = InstagramContentPipeline(
        image_publisher=mock_image_publisher,
        reel_publisher=mock_reel_publisher,
        dry_run=True,
    )

    content = InstagramContent(
        title="Headline",
        summary="Summary text",
        media_type="AUDIO",
    )

    result = pipeline.process_content(content)
    assert result.success is False
    assert "Unsupported media_type" in result.message


def test_custom_caption_and_hashtags(mock_image_publisher, mock_reel_publisher):
    pipeline = InstagramContentPipeline(
        image_publisher=mock_image_publisher,
        reel_publisher=mock_reel_publisher,
        dry_run=True,
    )

    content = InstagramContent(
        title="Headline",
        summary="Summary",
        caption="Custom caption provided by user #CustomTag",
        image_url="https://example.com/image.jpg",
        media_type="IMAGE",
    )

    result = pipeline.process_content(content)
    assert result.success is True
    assert "Custom caption provided" in result.caption
    assert "#TechCricketHub" in result.hashtags


def test_image_validation_failure(mock_image_publisher, mock_reel_publisher):
    mock_image_publisher.validate_image_url.side_effect = InstagramError("Invalid image URL scheme")

    pipeline = InstagramContentPipeline(
        image_publisher=mock_image_publisher,
        reel_publisher=mock_reel_publisher,
        dry_run=True,
    )

    content = InstagramContent(
        title="Title",
        summary="Summary",
        image_url="http://invalid-scheme.com/image.jpg",
        media_type="IMAGE",
    )

    result = pipeline.process_content(content)
    assert result.success is False
    assert "Invalid image URL scheme" in result.message


def test_api_error_in_real_publishing(mock_image_publisher, mock_reel_publisher):
    mock_image_publisher.publish_image.return_value = ImagePublishResult(
        success=False,
        creation_id="17900000000000001",
        media_id=None,
        message="OAuth token error during publish",
    )

    pipeline = InstagramContentPipeline(
        image_publisher=mock_image_publisher,
        reel_publisher=mock_reel_publisher,
        dry_run=False,
    )

    content = InstagramContent(
        title="Title",
        summary="Summary",
        image_url="https://example.com/image.jpg",
        media_type="IMAGE",
    )

    result = pipeline.process_content(content)
    assert result.success is False
    assert result.status == "FAILED"
    assert "OAuth token error" in result.message


def test_secret_redaction_in_pipeline_result():
    token = "EAACEdEose0cBA123SECRET"
    result = PipelineResult(
        success=False,
        dry_run=True,
        media_type="IMAGE",
        message=f"Error containing access_token={token}",
        error=f"Error containing access_token={token}",
    )

    repr_str = repr(result)
    str_str = str(result)

    assert token not in repr_str
    assert token not in str_str
    assert "[REDACTED]" in repr_str
    assert "[REDACTED]" in str_str
