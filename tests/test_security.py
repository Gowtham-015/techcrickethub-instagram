import logging
from security import RedactingFormatter, redact_token, redact_url


def test_redact_token_pattern():
    raw_text = "Fetching data with access_token=EAACEdEose0cBA123456789 and params"
    redacted = redact_token(raw_text)
    assert "EAACEdEose0cBA123456789" not in redacted
    assert "access_token=[REDACTED]" in redacted


def test_redact_token_explicit_string():
    token = "MY_SECRET_TOKEN_999"
    raw_text = f"An error occurred while using token {token} in request."
    redacted = redact_token(raw_text, token=token)
    assert token not in redacted
    assert "[REDACTED]" in redacted


def test_redact_token_multiple_occurrences():
    token = "SECRET_TOKEN_ABC"
    raw_text = f"Token 1: access_token={token}&other=123. Token 2: {token}"
    redacted = redact_token(raw_text, token=token)
    assert token not in redacted
    assert redacted.count("[REDACTED]") >= 2


def test_redact_url():
    url = "https://graph.facebook.com/v26.0/me?fields=id,name&access_token=SECRET_ACCESS_TOKEN_123"
    redacted = redact_url(url)
    assert "SECRET_ACCESS_TOKEN_123" not in redacted
    assert "access_token=[REDACTED]" in redacted


def test_redacting_formatter():
    token = "SUPER_SECRET_ACCESSTOKEN_456"
    formatter = RedactingFormatter(fmt="%(levelname)s: %(message)s", token=token)

    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg=f"Request to URL with access_token={token} failed.",
        args=(),
        exc_info=None,
    )

    formatted_msg = formatter.format(record)
    assert token not in formatted_msg
    assert "[REDACTED]" in formatted_msg
