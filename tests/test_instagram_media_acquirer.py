from unittest.mock import MagicMock, patch
import pytest
import requests

from exceptions import InstagramConnectionError, InstagramError, InstagramTimeoutError
from instagram_media_acquirer import InstagramMediaAcquirer


@patch("requests.head")
def test_acquire_media_image_success(mock_head):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {
        "Content-Type": "image/jpeg",
        "Content-Length": "1048576",
    }
    mock_head.return_value = mock_resp

    acquirer = InstagramMediaAcquirer()
    asset = acquirer.acquire_media("https://example.com/image.jpg", media_type="IMAGE")

    assert asset.media_type == "IMAGE"
    assert asset.url == "https://example.com/image.jpg"
    assert asset.content_type == "image/jpeg"
    assert asset.size_bytes == 1048576
    assert asset.status_code == 200
    assert asset.is_https is True


@patch("requests.head")
def test_acquire_media_reel_success(mock_head):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {
        "Content-Type": "video/mp4",
        "Content-Length": "10485760",
    }
    mock_head.return_value = mock_resp

    acquirer = InstagramMediaAcquirer()
    asset = acquirer.acquire_media("https://example.com/video.mp4", media_type="REEL")

    assert asset.media_type == "REEL"
    assert asset.content_type == "video/mp4"
    assert asset.size_bytes == 10485760


def test_acquire_media_invalid_url_scheme():
    acquirer = InstagramMediaAcquirer()
    with pytest.raises(InstagramError) as exc_info:
        acquirer.acquire_media("http://insecure.com/image.jpg", media_type="IMAGE")
    assert "Instagram requires HTTPS URLs" in str(exc_info.value)


@patch("requests.head")
def test_acquire_media_http_error(mock_head):
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_head.return_value = mock_resp

    acquirer = InstagramMediaAcquirer()
    with pytest.raises(InstagramConnectionError) as exc_info:
        acquirer.acquire_media("https://example.com/missing.jpg", media_type="IMAGE")
    assert "returned HTTP status error 404" in str(exc_info.value)


@patch("requests.head")
def test_acquire_media_timeout(mock_head):
    mock_head.side_effect = requests.Timeout("Connection timed out")

    acquirer = InstagramMediaAcquirer(timeout=5)
    with pytest.raises(InstagramTimeoutError) as exc_info:
        acquirer.acquire_media("https://example.com/slow.jpg", media_type="IMAGE")
    assert "timed out after 5s" in str(exc_info.value)


@patch("requests.head")
def test_acquire_media_invalid_content_type(mock_head):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"Content-Type": "text/html"}
    mock_head.return_value = mock_resp

    acquirer = InstagramMediaAcquirer()
    with pytest.raises(InstagramError) as exc_info:
        acquirer.acquire_media("https://example.com/media_stream", media_type="IMAGE")
    assert "returned non-image Content-Type 'text/html'" in str(exc_info.value)
