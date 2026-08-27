import time
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
    status: str = ""
    message: str = ""

    def __repr__(self) -> str:
        safe_msg = redact_token(self.message)
        return (
            f"PublishResult(success={self.success}, creation_id={self.creation_id!r}, "
            f"media_id={self.media_id!r}, status={self.status!r}, message={safe_msg!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()


class InstagramReelPublisher:
    """Service for publishing Reels (video) to an Instagram Business Account via Meta Graph API."""

    def __init__(
        self,
        client: Optional[InstagramAPIClient] = None,
        poll_interval_seconds: int = 5,
        max_attempts: int = 30,
    ):
        self.client = client or InstagramAPIClient()
        self.poll_interval_seconds = poll_interval_seconds
        self.max_attempts = max_attempts

    def validate_video_url(self, video_url: str) -> None:
        """Validates that the provided video URL satisfies Meta Instagram API requirements."""
        if not video_url or not isinstance(video_url, str) or not video_url.strip():
            raise InstagramError("Video URL is required and cannot be empty.", token=self.client.access_token)

        clean_url = video_url.strip()

        # Check for local file paths (Windows & Linux)
        if clean_url.startswith(("/", "\\")) or (len(clean_url) > 1 and clean_url[1] == ":"):
            raise InstagramError(
                "Invalid video URL: Local file paths are not allowed.",
                token=self.client.access_token,
            )

        parsed = urlparse(clean_url)

        if parsed.scheme.lower() != "https":
            raise InstagramError(
                f"Invalid video URL scheme: '{parsed.scheme}'. Instagram requires HTTPS URLs.",
                token=self.client.access_token,
            )

        hostname = (parsed.hostname or "").lower()
        if not hostname or hostname in ("localhost", "127.0.0.1", "0.0.0.0"):
            raise InstagramError(
                "Invalid video URL: Localhost or loopback addresses are not allowed.",
                token=self.client.access_token,
            )

        lowered_url = clean_url.lower()
        if "google.com/imgres" in lowered_url or "bing.com/images" in lowered_url or "google.com/url" in lowered_url:
            raise InstagramError(
                "Invalid video URL: Search engine result URLs are not direct video links.",
                token=self.client.access_token,
            )

        path = parsed.path.lower()
        if path.endswith((".html", ".htm", ".php", ".asp", ".aspx")):
            raise InstagramError(
                "Invalid video URL: Webpage URLs are not direct video links.",
                token=self.client.access_token,
            )

    def get_container_status(self, creation_id: str) -> dict:
        """Fetches the processing status of an Instagram media container."""
        return self.client.get(f"/{creation_id}", params={"fields": "status_code,status"})

    def create_reel_container(self, video_url: str, caption: Optional[str] = None) -> PublishResult:
        """Creates a Reel media container on Meta Graph API and returns creation_id."""
        self.validate_video_url(video_url)
        payload = {
            "media_type": "REELS",
            "video_url": video_url.strip(),
        }
        if caption and isinstance(caption, str) and caption.strip():
            payload["caption"] = caption.strip()

        res = self.client.post(f"/{self.client.user_id}/media", data=payload)
        creation_id = res.get("id")
        if not creation_id:
            return PublishResult(success=False, message="No container id returned by API.")
        return PublishResult(success=True, creation_id=str(creation_id), status="IN_PROGRESS")

    def publish_reel(self, video_url: str, caption: Optional[str] = None) -> PublishResult:
        """Executes the complete Reel container creation, status polling, and publishing workflow.
        
        Step 1: Validate video URL.
        Step 2: POST /{user_id}/media with media_type=REELS and video_url -> creation_id
        Step 3: GET /{creation_id}?fields=status_code,status until status is FINISHED.
        Step 4: POST /{user_id}/media_publish with creation_id -> media_id
        """
        creation_id: Optional[str] = None
        try:
            # 1. Validate video URL format & scheme
            self.validate_video_url(video_url)

            # 1b. Validate PUBLIC media accessibility externally via HTTP GET
            from instagram_media_verifier import InstagramMediaVerifier
            public_check = InstagramMediaVerifier.validate_meta_media_accessibility(video_url, media_type="REEL")
            if not public_check.get("is_valid"):
                err_msg = f"MEDIA_PUBLICATION_BLOCKED: {public_check.get('error', 'Public URL verification failed')}"
                self.client.logger.error(err_msg)
                return PublishResult(
                    success=False,
                    creation_id=None,
                    media_id=None,
                    status="MEDIA_FAILED",
                    message=err_msg,
                )

            # 2. Acquire Atomic Publish Lock for Meta API calls
            from instagram_publish_lock import InstagramPublishLock
            with InstagramPublishLock(timeout_seconds=10.0):
                # Create Reel media container
                payload = {
                    "media_type": "REELS",
                    "video_url": video_url.strip(),
                }
                if caption and isinstance(caption, str) and caption.strip():
                    payload["caption"] = caption.strip()

                self.client.logger.info(f"Creating Reel media container for user {self.client.user_id}...")
                container_response = self.client.post(
                    f"/{self.client.user_id}/media",
                    data=payload,
                )

                creation_id = container_response.get("id")
                if not creation_id:
                    raise InstagramAPIError(
                        "Reel container creation succeeded but no 'id' (creation_id) was returned by Meta API.",
                        token=self.client.access_token,
                    )

                self.client.logger.info(f"Reel container created successfully. creation_id: {creation_id}")

                # 3. Poll container processing status
                is_finished = False
                last_status = "UNKNOWN"

                for attempt in range(1, self.max_attempts + 1):
                    self.client.logger.info(
                        f"Checking Reel container status for {creation_id} (Attempt {attempt}/{self.max_attempts})..."
                    )
                    status_data = self.get_container_status(creation_id)
                    status_code = str(status_data.get("status_code", "")).upper()
                    last_status = status_code or str(status_data.get("status", "UNKNOWN"))

                    if status_code == "FINISHED":
                        is_finished = True
                        self.client.logger.info("Reel container status is FINISHED.")
                        break
                    elif status_code == "ERROR":
                        err_msg = status_data.get("status", "Container processing failed with ERROR status.")
                        raise InstagramAPIError(
                            f"Reel processing failed on Meta servers: {err_msg}",
                            token=self.client.access_token,
                        )
                    elif status_code == "EXPIRED":
                        raise InstagramAPIError(
                            "Reel container expired before publishing. Please recreate container.",
                            token=self.client.access_token,
                        )
                    elif status_code == "IN_PROGRESS" or not status_code:
                        self.client.logger.info(f"Reel processing in progress. Status: {last_status}")
                        if attempt < self.max_attempts:
                            time.sleep(self.poll_interval_seconds)

                if not is_finished:
                    raise InstagramAPIError(
                        f"Reel container status polling timed out after {self.max_attempts} attempts. Last status: {last_status}",
                        token=self.client.access_token,
                    )

                # 4. Publish Reel container
                self.client.logger.info(f"Publishing Reel container {creation_id}...")
                publish_response = self.client.post(
                    f"/{self.client.user_id}/media_publish",
                    data={"creation_id": creation_id},
                )

                media_id = publish_response.get("id")
                if not media_id:
                    raise InstagramAPIError(
                        "Reel publish request succeeded but no 'id' (media_id) was returned by Meta API.",
                        token=self.client.access_token,
                    )

                self.client.logger.info(f"Instagram Reel published successfully. media_id: {media_id}")

                # 5. Post-publish Meta Graph API verification
                is_confirmed = False
                try:
                    is_confirmed = self.client.verify_published_media(str(media_id))
                except Exception:
                    is_confirmed = False

                status_label = "PUBLISHED_CONFIRMED" if is_confirmed else "PUBLISHED"
                msg = (
                    "Instagram Reel published successfully and verified on Meta API."
                    if is_confirmed
                    else "Instagram Reel published successfully (Pending API propagation)."
                )


                return PublishResult(
                    success=True,
                    creation_id=str(creation_id),
                    media_id=str(media_id),
                    status=status_label,
                    message=msg,
                )


        except InstagramError as e:
            msg = redact_token(str(e), token=self.client.access_token)
            self.client.logger.error(f"Reel publishing failed: {msg}")
            return PublishResult(
                success=False,
                creation_id=str(creation_id) if creation_id else None,
                media_id=None,
                status="FAILED",
                message=msg,
            )
        except Exception as e:
            msg = redact_token(str(e), token=self.client.access_token)
            self.client.logger.error(f"Unexpected error during Reel publishing: {msg}")
            return PublishResult(
                success=False,
                creation_id=str(creation_id) if creation_id else None,
                media_id=None,
                status="FAILED",
                message=f"Unexpected error: {msg}",
            )
