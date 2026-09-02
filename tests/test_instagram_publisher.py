from unittest.mock import MagicMock, patch
import pytest

from exceptions import (
    InstagramAPIError,
    InstagramConnectionError,
    InstagramError,
    InstagramTimeoutError,
)
from instagram_client import InstagramAPIClient
from instagram_publisher import InstagramImagePublisher, PublishResult


@pytest.fixture(autouse=True)
def mock_media_verifier():
    with patch("instagram_media_verifier.InstagramMediaVerifier.validate_meta_media_accessibility", return_value={"is_valid": True}), \
         patch("requests.head") as mock_h, \
         patch("requests.get") as mock_g:
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"Content-Type": "image/jpeg"}
        mock_h.return_value = resp
        mock_g.return_value = resp
        yield


@pytest.fixture
def mock_client():
    client = MagicMock(spec=InstagramAPIClient)
    client.user_id = "37982406558040899"
    client.access_token = "SECRET_TOKEN_ABC123"
    client.logger = MagicMock()
    return client


def test_publish_image_success(mock_client):
    mock_client.post.side_effect = [
        {"id": "17900000000000001"},
        {"id": "17900000000000002"},
    ]

    publisher = InstagramImagePublisher(client=mock_client)
    res = publisher.publish_image(
        image_url="https://i.ytimg.com/vi/pbYX4gp_5kE/maxresdefault.jpg",
        caption="Test caption",
    )

    assert res.success is True
    assert res.creation_id == "17900000000000001"
    assert res.media_id == "17900000000000002"
    assert "successfully" in res.message

    assert mock_client.post.call_count == 2
    mock_client.post.assert_any_call(
        "/37982406558040899/media",
        data={
            "image_url": "https://i.ytimg.com/vi/pbYX4gp_5kE/maxresdefault.jpg",
            "caption": "Test caption",
        },
    )
    mock_client.post.assert_any_call(
        "/37982406558040899/media_publish",
        data={"creation_id": "17900000000000001"},
    )


def test_publish_image_no_caption(mock_client):
    mock_client.post.side_effect = [
        {"id": "17900000000000001"},
        {"id": "17900000000000002"},
    ]

    publisher = InstagramImagePublisher(client=mock_client)
    res = publisher.publish_image(image_url="https://example.com/image.jpg")

    assert res.success is True
    mock_client.post.assert_any_call(
        "/37982406558040899/media",
        data={"image_url": "https://example.com/image.jpg"},
    )


def test_missing_image_url(mock_client):
    publisher = InstagramImagePublisher(client=mock_client)
    res = publisher.publish_image(image_url="")
    assert res.success is False
    assert "Image URL is required" in res.message


@pytest.mark.parametrize(
    "invalid_url",
    [
        "http://example.com/image.jpg",
        "C:\\image.jpg",
        "/var/tmp/image.png",
        "https://localhost/image.jpg",
        "https://127.0.0.1/image.jpg",
        "https://google.com/imgres?imgurl=abc",
        "https://bing.com/images/search?q=test",
        "https://example.com/page.html",
    ],
)
def test_invalid_urls(mock_client, invalid_url):
    publisher = InstagramImagePublisher(client=mock_client)
    res = publisher.publish_image(image_url=invalid_url)
    assert res.success is False
    assert "Invalid image URL" in res.message


def test_container_creation_api_error(mock_client):
    mock_client.post.side_effect = InstagramAPIError(
        "Invalid image URL provided to Meta API",
        error_code=100,
        token="SECRET_TOKEN_ABC123",
    )

    publisher = InstagramImagePublisher(client=mock_client)
    res = publisher.publish_image("https://example.com/valid.jpg")

    assert res.success is False
    assert res.creation_id is None
    assert "Invalid image URL provided" in res.message
    assert "SECRET_TOKEN_ABC123" not in res.message


def test_publishing_api_error(mock_client):
    mock_client.post.side_effect = [
        {"id": "17900000000000001"},
        InstagramAPIError(
            "Media container not ready",
            error_code=9007,
            token="SECRET_TOKEN_ABC123",
        ),
    ]

    publisher = InstagramImagePublisher(client=mock_client)
    res = publisher.publish_image("https://example.com/valid.jpg")

    assert res.success is False
    assert res.creation_id == "17900000000000001"
    assert res.media_id is None
    assert "Media container not ready" in res.message


def test_missing_creation_id(mock_client):
    mock_client.post.return_value = {}

    publisher = InstagramImagePublisher(client=mock_client)
    res = publisher.publish_image("https://example.com/valid.jpg")

    assert res.success is False
    assert "no 'id' (creation_id) was returned" in res.message


def test_missing_media_id(mock_client):
    mock_client.post.side_effect = [
        {"id": "17900000000000001"},
        {},
    ]

    publisher = InstagramImagePublisher(client=mock_client)
    res = publisher.publish_image("https://example.com/valid.jpg")

    assert res.success is False
    assert res.creation_id == "17900000000000001"
    assert "no 'id' (media_id) was returned" in res.message


def test_timeout_error(mock_client):
    mock_client.post.side_effect = InstagramTimeoutError(
        "Request timed out",
        token="SECRET_TOKEN_ABC123",
    )

    publisher = InstagramImagePublisher(client=mock_client)
    res = publisher.publish_image("https://example.com/valid.jpg")

    assert res.success is False
    assert "timed out" in res.message
    assert "SECRET_TOKEN_ABC123" not in res.message


def test_connection_error(mock_client):
    mock_client.post.side_effect = InstagramConnectionError(
        "Network error",
        token="SECRET_TOKEN_ABC123",
    )

    publisher = InstagramImagePublisher(client=mock_client)
    res = publisher.publish_image("https://example.com/valid.jpg")

    assert res.success is False
    assert "Network error" in res.message
    assert "SECRET_TOKEN_ABC123" not in res.message


def test_publish_result_secret_redaction(mock_client):
    token = "SECRET_TOKEN_ABC123"
    result = PublishResult(
        success=False,
        creation_id="123",
        media_id=None,
        message=f"Failed request with access_token={token}",
    )

    repr_str = repr(result)
    assert token not in repr_str
    assert "[REDACTED]" in repr_str
