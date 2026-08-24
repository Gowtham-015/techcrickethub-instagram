import pytest
from config import Config
from exceptions import InstagramConfigError


def test_valid_config():
    config = Config(
        user_id="37982406558040899",
        access_token="test_secret_token_123",
        api_version="v26.0",
        timeout_seconds=30.0,
        log_level="INFO",
    )
    config.validate()
    assert config.user_id == "37982406558040899"
    assert config.access_token == "test_secret_token_123"
    assert config.api_version == "v26.0"
    assert config.timeout_seconds == 30.0


def test_missing_user_id():
    config = Config(
        user_id="",
        access_token="test_secret_token_123",
    )
    with pytest.raises(InstagramConfigError) as exc_info:
        config.validate()
    assert "INSTAGRAM_USER_ID is required" in str(exc_info.value)


def test_missing_access_token():
    config = Config(
        user_id="37982406558040899",
        access_token="",
    )
    with pytest.raises(InstagramConfigError) as exc_info:
        config.validate()
    assert "INSTAGRAM_ACCESS_TOKEN is missing" in str(exc_info.value)


def test_placeholder_access_token():
    config = Config(
        user_id="37982406558040899",
        access_token="YOUR_ACCESS_TOKEN_HERE",
    )
    with pytest.raises(InstagramConfigError) as exc_info:
        config.validate()
    assert "INSTAGRAM_ACCESS_TOKEN is missing or set to placeholder" in str(exc_info.value)


def test_invalid_timeout():
    config = Config(
        user_id="37982406558040899",
        access_token="test_secret_token_123",
        timeout_seconds=0,
    )
    with pytest.raises(InstagramConfigError) as exc_info:
        config.validate()
    assert "INSTAGRAM_TIMEOUT_SECONDS must be > 0" in str(exc_info.value)


def test_invalid_api_version_format():
    config = Config(
        user_id="37982406558040899",
        access_token="test_secret_token_123",
        api_version="26.0",
    )
    with pytest.raises(InstagramConfigError) as exc_info:
        config.validate()
    assert "Invalid INSTAGRAM_API_VERSION format" in str(exc_info.value)


def test_env_loading(monkeypatch):
    monkeypatch.setenv("INSTAGRAM_USER_ID", "123456789")
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "valid_token_abc")
    monkeypatch.setenv("INSTAGRAM_API_VERSION", "v26.0")
    monkeypatch.setenv("INSTAGRAM_TIMEOUT_SECONDS", "15.5")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    config = Config.load_from_env(env_path="")
    assert config.user_id == "123456789"
    assert config.access_token == "valid_token_abc"
    assert config.timeout_seconds == 15.5
    assert config.log_level == "DEBUG"


def test_invalid_timeout_str_in_env(monkeypatch):
    monkeypatch.setenv("INSTAGRAM_USER_ID", "123456789")
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "valid_token_abc")
    monkeypatch.setenv("INSTAGRAM_TIMEOUT_SECONDS", "invalid_number")

    with pytest.raises(InstagramConfigError) as exc_info:
        Config.load_from_env(env_path="")
    assert "Invalid INSTAGRAM_TIMEOUT_SECONDS value" in str(exc_info.value)


def test_config_token_redaction_repr():
    config = Config(
        user_id="37982406558040899",
        access_token="SUPER_SECRET_TOKEN_XYZ",
    )
    repr_str = repr(config)
    assert "SUPER_SECRET_TOKEN_XYZ" not in repr_str
    assert "[REDACTED]" in repr_str
