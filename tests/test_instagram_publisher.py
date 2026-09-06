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


@pytest.fixture
def mock_client():
    client = MagicMock(spec=InstagramAPIClient)
    client.user_id = "37982406558040899"
    client.access_token = "SECRET_TOKEN_ABC123"
    client.logger = MagicMock()
    return client


def test_publish_image_prohibited_reel_only(mock_client):
    """Verify InstagramImagePublisher.publish_image fails closed on IMAGE publication."""
    publisher = InstagramImagePublisher(client=mock_client)
    with pytest.raises(InstagramError) as exc_info:
        publisher.publish_image("https://example.com/image.jpg", caption="Test caption")
    assert "100% Reel-only publishing is enforced" in str(exc_info.value)


def test_missing_image_url_validation(mock_client):
    publisher = InstagramImagePublisher(client=mock_client)
    with pytest.raises(InstagramError) as exc_info:
        publisher.validate_image_url("")
    assert "Image URL is required" in str(exc_info.value)


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
def test_invalid_urls_validation(mock_client, invalid_url):
    publisher = InstagramImagePublisher(client=mock_client)
    with pytest.raises(InstagramError) as exc_info:
        publisher.validate_image_url(invalid_url)
    assert "Invalid image URL" in str(exc_info.value)


def test_publish_result_secret_redaction():
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
