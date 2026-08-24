from typing import Optional
from security import redact_token


class InstagramError(Exception):
    """Base exception for Instagram API operations."""

    def __init__(self, message: str, token: Optional[str] = None):
        self.raw_message = message
        self.token = token
        self.message = redact_token(str(message), token=token)
        super().__init__(self.message)

    def __str__(self) -> str:
        return redact_token(self.message, token=self.token)

    def __repr__(self) -> str:
        cls_name = self.__class__.__name__
        sanitized_msg = redact_token(self.message, token=self.token)
        return f"{cls_name}(message={sanitized_msg!r})"


class InstagramConfigError(InstagramError):
    """Raised when Instagram configuration is missing or invalid."""
    pass


class InstagramAPIError(InstagramError):
    """Raised when Meta Instagram API returns an error response."""

    def __init__(
        self,
        message: str,
        error_code: Optional[int] = None,
        error_subcode: Optional[int] = None,
        error_type: Optional[str] = None,
        fbtrace_id: Optional[str] = None,
        http_status: Optional[int] = None,
        token: Optional[str] = None,
    ):
        self.error_code = error_code
        self.error_subcode = error_subcode
        self.error_type = error_type
        self.fbtrace_id = fbtrace_id
        self.http_status = http_status
        super().__init__(message, token=token)

    def __repr__(self) -> str:
        cls_name = self.__class__.__name__
        sanitized_msg = redact_token(self.message, token=self.token)
        return (
            f"{cls_name}(message={sanitized_msg!r}, error_code={self.error_code}, "
            f"error_subcode={self.error_subcode}, error_type={self.error_type!r}, "
            f"fbtrace_id={self.fbtrace_id!r}, http_status={self.http_status})"
        )


class InstagramConnectionError(InstagramError):
    """Raised when network connection to Instagram API fails."""
    pass


class InstagramTimeoutError(InstagramError):
    """Raised when request to Instagram API times out."""
    pass
