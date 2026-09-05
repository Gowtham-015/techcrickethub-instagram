from unittest.mock import MagicMock, patch
import pytest

from exceptions import (
    InstagramAPIError,
    InstagramConnectionError,
    InstagramError,
    InstagramTimeoutError,
)
from instagram_client import InstagramAPIClient
from instagram_reel_publisher import InstagramReelPublisher, PublishResult


@pytest.fixture
def mock_client():
    client = MagicMock(spec=InstagramAPIClient)
    client.user_id = "37982406558040899"
    client.access_token = "SECRET_REEL_TOKEN_999"
    client.logger = MagicMock()
    return client


@pytest.fixture(autouse=True)
def mock_media_verifier():
    with patch("instagram_media_verifier.InstagramMediaVerifier.validate_meta_media_accessibility", return_value={"is_valid": True}):
        yield


def test_publish_reel_success(mock_client):
    mock_client.post.side_effect = [
        {"id": "18000000000000001"},
        {"id": "18000000000000002"},
    ]
    mock_client.get.return_value = {"status_code": "FINISHED", "status": "Finished processing"}

    publisher = InstagramReelPublisher(client=mock_client, poll_interval_seconds=0, max_attempts=5)
    res = publisher.publish_reel(
        video_url="https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4",
        caption="Sample Reel Caption",
    )

    assert res.success is True
    assert res.creation_id == "18000000000000001"
    assert res.media_id == "18000000000000002"
    assert res.status in ("PUBLISHED", "PUBLISHED_CONFIRMED")
    assert "successfully" in res.message

    mock_client.post.assert_any_call(
        "/37982406558040899/media",
        data={
            "media_type": "REELS",
            "video_url": "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4",
            "caption": "Sample Reel Caption",
        },
    )
    mock_client.get.assert_called_once_with(
        "/18000000000000001",
        params={"fields": "status_code,status"},
    )
    mock_client.post.assert_any_call(
        "/37982406558040899/media_publish",
        data={"creation_id": "18000000000000001"},
    )


def test_publish_reel_no_caption(mock_client):
    mock_client.post.side_effect = [
        {"id": "18000000000000001"},
        {"id": "18000000000000002"},
    ]
    mock_client.get.return_value = {"status_code": "FINISHED"}

    publisher = InstagramReelPublisher(client=mock_client, poll_interval_seconds=0)
    res = publisher.publish_reel(video_url="https://example.com/video.mp4")

    assert res.success is True
    mock_client.post.assert_any_call(
        "/37982406558040899/media",
        data={
            "media_type": "REELS",
            "video_url": "https://example.com/video.mp4",
        },
    )


def test_missing_video_url(mock_client):
    publisher = InstagramReelPublisher(client=mock_client)
    res = publisher.publish_reel(video_url="")
    assert res.success is False
    assert "Video URL is required" in res.message


@pytest.mark.parametrize(
    "invalid_url",
    [
        "http://example.com/video.mp4",
        "C:\\video.mp4",
        "/home/user/video.mp4",
        "https://localhost/video.mp4",
        "https://127.0.0.1/video.mp4",
        "https://google.com/imgres?imgurl=abc",
        "https://bing.com/images/search?q=test",
        "https://example.com/page.html",
        "https://example.com/index.php",
        "https://www.youtube.com/watch?v=ihxHk6wYj8c",
        "https://youtu.be/ihxHk6wYj8c",
        "https://vimeo.com/123456",
        "https://www.tiktok.com/@user/video/1234",
    ],
)
def test_invalid_video_urls(mock_client, invalid_url):
    publisher = InstagramReelPublisher(client=mock_client)
    res = publisher.publish_reel(video_url=invalid_url)
    assert res.success is False
    assert "Invalid video URL" in res.message
    mock_client.post.assert_not_called()


def test_validate_video_url_rejects_youtube_watch_urls(mock_client):
    publisher = InstagramReelPublisher(client=mock_client)
    with pytest.raises(InstagramError) as exc_info:
        publisher.validate_video_url("https://www.youtube.com/watch?v=ihxHk6wYj8c")
    assert "Invalid video URL" in str(exc_info.value)
    assert "YouTube watch links" in str(exc_info.value)


@patch("time.sleep", return_value=None)
def test_in_progress_eventually_finished(mock_sleep, mock_client):
    mock_client.post.side_effect = [
        {"id": "18000000000000001"},
        {"id": "18000000000000002"},
    ]
    mock_client.get.side_effect = [
        {"status_code": "IN_PROGRESS", "status": "Downloading video"},
        {"status_code": "FINISHED", "status": "Ready"},
    ]

    publisher = InstagramReelPublisher(client=mock_client, poll_interval_seconds=1, max_attempts=5)
    res = publisher.publish_reel("https://example.com/video.mp4")

    assert res.success is True
    assert mock_client.get.call_count == 2
    mock_sleep.assert_called_once_with(1)


@patch("time.sleep", return_value=None)
def test_polling_max_attempts_exceeded(mock_sleep, mock_client):
    mock_client.post.return_value = {"id": "18000000000000001"}
    mock_client.get.return_value = {"status_code": "IN_PROGRESS", "status": "Processing"}

    publisher = InstagramReelPublisher(client=mock_client, poll_interval_seconds=0, max_attempts=3)
    res = publisher.publish_reel("https://example.com/video.mp4")

    assert res.success is False
    assert res.creation_id == "18000000000000001"
    assert "timed out after 3 attempts" in res.message


def test_container_error_status(mock_client):
    mock_client.post.return_value = {"id": "18000000000000001"}
    mock_client.get.return_value = {"status_code": "ERROR", "status": "Video resolution unsupported"}

    publisher = InstagramReelPublisher(client=mock_client, poll_interval_seconds=0)
    res = publisher.publish_reel("https://example.com/video.mp4")

    assert res.success is False
    assert res.creation_id == "18000000000000001"
    assert "Video resolution unsupported" in res.message


def test_container_expired_status(mock_client):
    mock_client.post.return_value = {"id": "18000000000000001"}
    mock_client.get.return_value = {"status_code": "EXPIRED", "status": "Expired"}

    publisher = InstagramReelPublisher(client=mock_client, poll_interval_seconds=0)
    res = publisher.publish_reel("https://example.com/video.mp4")

    assert res.success is False
    assert res.creation_id == "18000000000000001"
    assert "expired" in res.message.lower()


def test_container_creation_api_error(mock_client):
    mock_client.post.side_effect = InstagramAPIError(
        "Invalid video URL or format",
        error_code=100,
        token="SECRET_REEL_TOKEN_999",
    )

    publisher = InstagramReelPublisher(client=mock_client)
    res = publisher.publish_reel("https://example.com/video.mp4")

    assert res.success is False
    assert res.creation_id is None
    assert "Invalid video URL" in res.message
    assert "SECRET_REEL_TOKEN_999" not in res.message


def test_publishing_api_error(mock_client):
    mock_client.post.side_effect = [
        {"id": "18000000000000001"},
        InstagramAPIError(
            "OAuth error during Reel publish",
            error_code=190,
            token="SECRET_REEL_TOKEN_999",
        ),
    ]
    mock_client.get.return_value = {"status_code": "FINISHED"}

    publisher = InstagramReelPublisher(client=mock_client, poll_interval_seconds=0)
    res = publisher.publish_reel("https://example.com/video.mp4")

    assert res.success is False
    assert res.creation_id == "18000000000000001"
    assert res.media_id is None
    assert "OAuth error" in res.message


def test_missing_creation_id(mock_client):
    mock_client.post.return_value = {}

    publisher = InstagramReelPublisher(client=mock_client)
    res = publisher.publish_reel("https://example.com/video.mp4")

    assert res.success is False
    assert "no 'id' (creation_id) was returned" in res.message


def test_missing_media_id(mock_client):
    mock_client.post.side_effect = [
        {"id": "18000000000000001"},
        {},
    ]
    mock_client.get.return_value = {"status_code": "FINISHED"}

    publisher = InstagramReelPublisher(client=mock_client, poll_interval_seconds=0)
    res = publisher.publish_reel("https://example.com/video.mp4")

    assert res.success is False
    assert res.creation_id == "18000000000000001"
    assert "no 'id' (media_id) was returned" in res.message


@pytest.mark.parametrize("http_code", [400, 401, 403, 429, 500])
def test_http_api_errors(mock_client, http_code):
    mock_client.post.side_effect = InstagramAPIError(
        f"HTTP {http_code} Meta Error",
        http_status=http_code,
        token="SECRET_REEL_TOKEN_999",
    )

    publisher = InstagramReelPublisher(client=mock_client)
    res = publisher.publish_reel("https://example.com/video.mp4")

    assert res.success is False
    assert f"HTTP {http_code}" in res.message


def test_timeout_error(mock_client):
    mock_client.post.side_effect = InstagramTimeoutError("Request timed out", token="SECRET_REEL_TOKEN_999")

    publisher = InstagramReelPublisher(client=mock_client)
    res = publisher.publish_reel("https://example.com/video.mp4")

    assert res.success is False
    assert "timed out" in res.message
    assert "SECRET_REEL_TOKEN_999" not in res.message


def test_connection_error(mock_client):
    mock_client.post.side_effect = InstagramConnectionError("Network error", token="SECRET_REEL_TOKEN_999")

    publisher = InstagramReelPublisher(client=mock_client)
    res = publisher.publish_reel("https://example.com/video.mp4")

    assert res.success is False
    assert "Network error" in res.message
    assert "SECRET_REEL_TOKEN_999" not in res.message


def test_secret_redaction_in_publish_result(mock_client):
    token = "SECRET_REEL_TOKEN_999"
    res = PublishResult(
        success=False,
        creation_id="123",
        media_id=None,
        status="FAILED",
        message=f"Failed request with access_token={token}",
    )

    repr_str = repr(res)
    str_str = str(res)

    assert token not in repr_str
    assert token not in str_str
    assert "[REDACTED]" in repr_str
    assert "[REDACTED]" in str_str
