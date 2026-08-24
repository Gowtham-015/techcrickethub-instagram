from exceptions import (
    InstagramAPIError,
    InstagramConfigError,
    InstagramConnectionError,
    InstagramError,
    InstagramTimeoutError,
)


def test_base_instagram_error():
    token = "MY_PRIVATE_TOKEN"
    err = InstagramError(f"Failed with access_token={token}", token=token)
    assert token not in str(err)
    assert token not in repr(err)
    assert "[REDACTED]" in str(err)
    assert "[REDACTED]" in repr(err)


def test_instagram_config_error():
    err = InstagramConfigError("Config error occurred")
    assert isinstance(err, InstagramError)
    assert "Config error occurred" in str(err)


def test_instagram_api_error_attributes():
    token = "SECRET_API_TOKEN"
    err = InstagramAPIError(
        message=f"Invalid parameter with access_token={token}",
        error_code=100,
        error_subcode=33,
        error_type="OAuthException",
        fbtrace_id="AbCdEf12345",
        http_status=400,
        token=token,
    )

    assert err.error_code == 100
    assert err.error_subcode == 33
    assert err.error_type == "OAuthException"
    assert err.fbtrace_id == "AbCdEf12345"
    assert err.http_status == 400

    str_repr = str(err)
    repr_repr = repr(err)

    assert token not in str_repr
    assert token not in repr_repr
    assert "[REDACTED]" in str_repr
    assert "[REDACTED]" in repr_repr


def test_instagram_connection_error():
    token = "MY_TOKEN_777"
    err = InstagramConnectionError(f"Connection failed for access_token={token}", token=token)
    assert isinstance(err, InstagramError)
    assert token not in str(err)
    assert token not in repr(err)


def test_instagram_timeout_error():
    token = "MY_TOKEN_888"
    err = InstagramTimeoutError(f"Request timed out for access_token={token}", token=token)
    assert isinstance(err, InstagramError)
    assert token not in str(err)
    assert token not in repr(err)
