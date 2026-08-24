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
        creation_id: Optional[str] = None
        try:
            # 1. Validate image URL
            self.validate_image_url(image_url)

            # 2. Prepare container creation payload
            container_payload = {"image_url": image_url.strip()}
            if caption and isinstance(caption, str) and caption.strip():
                container_payload["caption"] = caption.strip()

            # 3. Create media container (Step 1)
            self.client.logger.info(f"Creating media container for user {self.client.user_id}...")
            container_response = self.client.post(
                f"/{self.client.user_id}/media",
                data=container_payload,
            )

            creation_id = container_response.get("id")
            if not creation_id:
                raise InstagramAPIError(
                    "Container creation succeeded but no 'id' (creation_id) was returned by Meta API.",
                    token=self.client.access_token,
                )

            self.client.logger.info(f"Media container created successfully. creation_id: {creation_id}")

            # 4. Check container status / wait for processing
            import time
            for attempt in range(1, 6):
                try:
                    status_res = self.client.get(f"/{creation_id}", params={"fields": "status_code"})
                    sc = str(status_res.get("status_code", "")).upper()
                    if sc in ("FINISHED", "READY", ""):
                        break
                    self.client.logger.info(f"Container status is '{sc}'. Waiting 2s for Meta processing...")
                    time.sleep(2)
                except Exception:
                    time.sleep(2)

            # 5. Publish media container (Step 2) with retry if processing
            media_id = None
            for pub_attempt in range(1, 4):
                try:
                    self.client.logger.info(f"Publishing container {creation_id} (Attempt {pub_attempt}/3)...")
                    publish_response = self.client.post(
                        f"/{self.client.user_id}/media_publish",
                        data={"creation_id": creation_id},
                    )
                    media_id = publish_response.get("id")
                    if media_id:
                        break
                except InstagramAPIError as e:
                    if "Media ID is not available" in str(e) and pub_attempt < 3:
                        self.client.logger.info("Meta container processing in progress. Retrying publish in 3s...")
                        time.sleep(3)
                        continue
                    raise e
            if not media_id:
                raise InstagramAPIError(
                    "Media publish request succeeded but no 'id' (media_id) was returned by Meta API.",
                    token=self.client.access_token,
                )

            self.client.logger.info(f"Image published successfully. media_id: {media_id}")

            return PublishResult(
                success=True,
                creation_id=str(creation_id),
                media_id=str(media_id),
                message="Image published successfully to Instagram.",
            )

        except InstagramError as e:
            msg = redact_token(str(e), token=self.client.access_token)
            self.client.logger.error(f"Image publishing failed: {msg}")
            return PublishResult(
                success=False,
                creation_id=str(creation_id) if creation_id else None,
                media_id=None,
                message=msg,
            )
        except Exception as e:
            msg = redact_token(str(e), token=self.client.access_token)
            self.client.logger.error(f"Unexpected error during image publishing: {msg}")
            return PublishResult(
                success=False,
                creation_id=str(creation_id) if creation_id else None,
                media_id=None,
                message=f"Unexpected error: {msg}",
            )
