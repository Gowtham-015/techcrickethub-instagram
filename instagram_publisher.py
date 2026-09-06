from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from exceptions import InstagramAPIError, InstagramError
from instagram_client import InstagramAPIClient
from security import redact_token


@dataclass
class PublishResult:
    success: bool
    creation_id: Optional[str] = None
    media_id: Optional[str] = None
    message: str = ""

    def __repr__(self) -> str:
        safe_msg = redact_token(self.message)
        return (
            f"PublishResult(success={self.success}, creation_id={self.creation_id!r}, "
            f"media_id={self.media_id!r}, message={safe_msg!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()


class InstagramImagePublisher:
    """Service for publishing images to an Instagram Business Account via Meta Graph API."""

    def __init__(self, client: Optional[InstagramAPIClient] = None):
        self.client = client or InstagramAPIClient()

    def validate_image_url(self, url: str) -> None:
        """Validates that the provided image URL satisfies Instagram API requirements."""
        if not url or not isinstance(url, str) or not url.strip():
            raise InstagramError("Image URL is required and cannot be empty.", token=self.client.access_token)

        clean_url = url.strip()

        # Check for local file paths
        if clean_url.startswith(("/", "\\")) or (len(clean_url) > 1 and clean_url[1] == ":"):
            raise InstagramError(
                "Invalid image URL: Local file paths are not allowed.",
                token=self.client.access_token,
            )

        parsed = urlparse(clean_url)

        if parsed.scheme.lower() != "https":
            raise InstagramError(
                f"Invalid image URL scheme: '{parsed.scheme}'. Instagram requires HTTPS URLs.",
                token=self.client.access_token,
            )

        hostname = (parsed.hostname or "").lower()
        if not hostname or hostname in ("localhost", "127.0.0.1", "0.0.0.0"):
            raise InstagramError(
                "Invalid image URL: Localhost or loopback addresses are not allowed.",
                token=self.client.access_token,
            )

        # Check for search engine or webpage result URLs
        lowered_url = clean_url.lower()
        if "google.com/imgres" in lowered_url or "bing.com/images" in lowered_url or "google.com/url" in lowered_url:
            raise InstagramError(
                "Invalid image URL: Search engine result URLs are not direct image links.",
                token=self.client.access_token,
            )

        path = parsed.path.lower()
        if path.endswith((".html", ".htm", ".php", ".asp", ".aspx")):
            raise InstagramError(
                "Invalid image URL: Webpage URLs are not direct image links.",
                token=self.client.access_token,
            )

    def publish_image(self, image_url: str, caption: Optional[str] = None) -> PublishResult:
        """Executes the 2-step Instagram image publishing flow.
        
        Step 1: POST /{user_id}/media with image_url and optional caption -> creation_id
        Step 2: POST /{user_id}/media_publish with creation_id -> media_id
        """
        raise InstagramError(
            "IMAGE publication is strictly prohibited. 100% Reel-only publishing is enforced in production.",
            token=self.client.access_token,
        )
