import logging
import re
from typing import Optional

# Regular expression pattern for access_token parameter in URLs or query strings
ACCESS_TOKEN_PARAM_REGEX = re.compile(r"(access_token=)[^&\s\"'\\]+", re.IGNORECASE)

REDACTED_LABEL = "[REDACTED]"


def redact_token(text: str, token: Optional[str] = None) -> str:
    """Redacts access tokens from strings, log messages, and URLs.
    
    Replaces pattern `access_token=...` with `access_token=[REDACTED]`.
    If an explicit token string is provided, also redacts exact instances of that token string.
    """
    if not isinstance(text, str):
        return text

    # Redact access_token=... query parameters or key-value pairs
    redacted_text = ACCESS_TOKEN_PARAM_REGEX.sub(r"\1" + REDACTED_LABEL, text)

    # Redact exact token string if supplied and valid
    if token and isinstance(token, str) and token.strip() and token != REDACTED_LABEL:
        redacted_text = redacted_text.replace(token, REDACTED_LABEL)

    return redacted_text


def redact_url(url: str, token: Optional[str] = None) -> str:
    """Redacts sensitive token parameters from a URL."""
    return redact_token(url, token=token)


class RedactingFormatter(logging.Formatter):
    """Logging formatter that automatically redacts access tokens from formatted output."""

    def __init__(self, fmt=None, datefmt=None, style='%', token: Optional[str] = None):
        super().__init__(fmt=fmt, datefmt=datefmt, style=style)
        self.token = token

    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        return redact_token(formatted, token=self.token)
