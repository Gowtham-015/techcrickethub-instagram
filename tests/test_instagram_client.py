from unittest.mock import MagicMock, patch
import pytest
import requests

from exceptions import (
    InstagramAPIError,
    InstagramConnectionError,
    InstagramTimeoutError,
)
from instagram_client import InstagramAPIClient


@pytest.fixture
def client():
    return InstagramAPIClient(
        user_id="37982406558040899",
        access_token="MOCK_ACCESS_TOKEN_12345",
        api_version="v26.0",
        timeout=10.0,
    )


@patch("requests.Session.request")
def test_successful_get(mock_request, client):
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "37982406558040899", "username": "techcrickethub"}
    mock_request.return_value = mock_resp

    result = client.get("/37982406558040899", params={"fields": "id,username"})

    assert result["id"] == "37982406558040899"
    assert result["username"] == "techcrickethub"

    mock_request.assert_called_once()
    call_kwargs = mock_request.call_args.kwargs
    assert call_kwargs["method"] == "GET"
    assert call_kwargs["url"] == "https://graph.instagram.com/v26.0/37982406558040899"
    assert call_kwargs["params"]["access_token"] == "MOCK_ACCESS_TOKEN_12345"
    assert call_kwargs["params"]["fields"] == "id,username"


@patch("requests.Session.request")
def test_successful_post(mock_request, client):
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "17841400000000001"}
    mock_request.return_value = mock_resp

    result = client.post("/37982406558040899/media", data={"caption": "Hello world"})

    assert result["id"] == "17841400000000001"
    mock_request.assert_called_once()
    call_kwargs = mock_request.call_args.kwargs
    assert call_kwargs["method"] == "POST"
    assert call_kwargs["data"] == {"caption": "Hello world"}


@patch("requests.Session.request")
def test_http_400_meta_error_json(mock_request, client):
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 400
    mock_resp.json.return_value = {
        "error": {
            "message": "Invalid OAuth access token.",
            "type": "OAuthException",
            "code": 190,
            "error_subcode": 463,
            "fbtrace_id": "FzX9A1B2C3D",
        }
    }
    mock_request.return_value = mock_resp

    with pytest.raises(InstagramAPIError) as exc_info:
        client.get("/me")

    err = exc_info.value
    assert err.error_code == 190
    assert err.error_subcode == 463
    assert err.error_type == "OAuthException"
    assert err.fbtrace_id == "FzX9A1B2C3D"
    assert err.http_status == 400
    assert "Invalid OAuth access token" in str(err)


@patch("requests.Session.request")
def test_http_401_meta_error_json(mock_request, client):
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 401
    mock_resp.json.return_value = {
        "error": {
            "message": "Session has expired.",
            "type": "OAuthException",
            "code": 190,
        }
    }
    mock_request.return_value = mock_resp

    with pytest.raises(InstagramAPIError) as exc_info:
        client.get("/me")

    err = exc_info.value
    assert err.http_status == 401
    assert err.error_code == 190


@patch("requests.Session.request")
def test_http_500_meta_error(mock_request, client):
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 500
    mock_resp.json.return_value = {
        "error": {
            "message": "An unknown error occurred.",
            "type": "FacebookApiException",
            "code": 1,
        }
    }
    mock_request.return_value = mock_resp

    with pytest.raises(InstagramAPIError) as exc_info:
        client.get("/me")

    err = exc_info.value
    assert err.http_status == 500
    assert err.error_code == 1


@patch("requests.Session.request")
def test_request_timeout(mock_request, client):
    mock_request.side_effect = requests.exceptions.Timeout("Connection timed out")

    with pytest.raises(InstagramTimeoutError) as exc_info:
        client.get("/me")

    assert "timed out" in str(exc_info.value)
    assert client.access_token not in str(exc_info.value)


@patch("requests.Session.request")
def test_connection_failure(mock_request, client):
    mock_request.side_effect = requests.exceptions.ConnectionError("Failed to establish a new connection")

    with pytest.raises(InstagramConnectionError) as exc_info:
        client.get("/me")

    assert "connection" in str(exc_info.value).lower()
    assert client.access_token not in str(exc_info.value)


@patch("requests.Session.request")
def test_malformed_json(mock_request, client):
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.json.side_effect = ValueError("Invalid JSON")
    mock_request.return_value = mock_resp

    with pytest.raises(InstagramAPIError) as exc_info:
        client.get("/me")

    assert "parse JSON response" in str(exc_info.value)


@patch("requests.Session.request")
def test_secret_redaction_in_exception(mock_request, client):
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 400
    mock_resp.json.return_value = {
        "error": {
            "message": "Error with token MOCK_ACCESS_TOKEN_12345 in URL",
            "type": "OAuthException",
            "code": 100,
        }
    }
    mock_request.return_value = mock_resp

    with pytest.raises(InstagramAPIError) as exc_info:
        client.get("/me")

    err_str = str(exc_info.value)
    err_repr = repr(exc_info.value)

    assert "MOCK_ACCESS_TOKEN_12345" not in err_str
    assert "MOCK_ACCESS_TOKEN_12345" not in err_repr
    assert "[REDACTED]" in err_str
