import logging
from typing import Optional
import requests
from exceptions import InstagramConnectionError, InstagramError, InstagramTimeoutError
from instagram_media_metadata import MediaAsset
from instagram_publisher import InstagramImagePublisher
from instagram_reel_publisher import InstagramReelPublisher


class InstagramMediaAcquirer:
    """Acquires and verifies remote media metadata using safe HTTP HEAD requests and existing validators."""

    def __init__(
        self,
        image_publisher: Optional[InstagramImagePublisher] = None,
        reel_publisher: Optional[InstagramReelPublisher] = None,
        timeout: int = 15,
    ):
        self.timeout = timeout
        self.image_publisher = image_publisher or InstagramImagePublisher()
        self.reel_publisher = reel_publisher or InstagramReelPublisher()
        self.logger = logging.getLogger("InstagramMediaAcquirer")

    def acquire_media(self, url: str, media_type: str) -> MediaAsset:
        """Validates media URL syntax, performs a safe HTTP HEAD request to extract metadata,
        and verifies MIME content types without downloading full payloads.
        """
        media_type_clean = (media_type or "IMAGE").strip().upper()

        # Step 1: Validate URL using Phase 2/3 validators
        if media_type_clean == "IMAGE":
            self.image_publisher.validate_image_url(url)
        elif media_type_clean == "REEL":
            self.reel_publisher.validate_video_url(url)
        else:
            raise InstagramError(f"Unsupported media_type: '{media_type}'. Expected 'IMAGE' or 'REEL'.")

        # Step 2: Safe remote verification via HTTP HEAD
        status_code = None
        content_type = None
        size_bytes = None

        try:
            resp = requests.head(url, allow_redirects=True, timeout=self.timeout)
            status_code = resp.status_code

            if status_code >= 400:
                raise InstagramConnectionError(
                    f"Remote media server returned HTTP status error {status_code} for URL: '{url}'"
                )

            content_type = resp.headers.get("Content-Type", "").strip().lower()
            length_header = resp.headers.get("Content-Length", "").strip()
            if length_header.isdigit():
                size_bytes = int(length_header)

        except requests.Timeout:
            raise InstagramTimeoutError(f"HTTP HEAD request timed out after {self.timeout}s for URL: '{url}'")
        except requests.RequestException as e:
            raise InstagramConnectionError(f"Failed to connect to remote media server: {e}")
        except InstagramError:
            raise
        except Exception as e:
            raise InstagramConnectionError(f"Unexpected error inspecting remote media: {e}")

        # Step 3: Validate Content-Type if present
        if content_type:
            if media_type_clean == "IMAGE":
                if "text/html" in content_type or "application/json" in content_type:
                    raise InstagramError(
                        f"Media URL returned non-image Content-Type '{content_type}': '{url}'"
                    )
            elif media_type_clean == "REEL":
                if "text/html" in content_type or "image/" in content_type or "application/json" in content_type:
                    raise InstagramError(
                        f"Media URL returned non-video Content-Type '{content_type}': '{url}'"
                    )

        asset = MediaAsset.from_url(
            url=url,
            media_type=media_type_clean,
            content_type=content_type,
            size_bytes=size_bytes,
            status_code=status_code,
        )

        self.logger.info(
            f"Acquired media asset [{media_type_clean}] from {asset.source_host} "
            f"(Content-Type: {content_type or 'unknown'}, Size: {size_bytes or 'unknown'})"
        )
        return asset
