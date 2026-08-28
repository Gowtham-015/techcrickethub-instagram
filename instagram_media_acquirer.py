import logging
import os
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

        # Check local file resolution first for generated reels and cards
        base_dir = os.path.dirname(os.path.abspath(__file__))
        filename = os.path.basename(url.split("?")[0])
        for sub in (os.path.join("data", "generated_reels"), os.path.join("media", "generated")):
            cand = os.path.join(base_dir, sub, filename)
            if os.path.exists(cand):
                size_b = os.path.getsize(cand)
                c_type = "video/mp4" if media_type_clean == "REEL" else "image/jpeg"
                self.logger.info(f"Acquired local media asset [{media_type_clean}] for {url} ({size_b} bytes)")
                return MediaAsset.from_url(
                    url=url,
                    media_type=media_type_clean,
                    content_type=c_type,
                    size_bytes=size_b,
                    status_code=200,
                )

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }

        try:
            try:
                resp = requests.head(url, allow_redirects=True, headers=headers, timeout=self.timeout)
                status_code = resp.status_code
                content_type = resp.headers.get("Content-Type", "").strip().lower()
                length_header = resp.headers.get("Content-Length", "").strip()
            except Exception:
                # Fallback to streaming GET request if HEAD is blocked or disconnected by WAF/CDN
                resp = requests.get(url, allow_redirects=True, headers=headers, stream=True, timeout=self.timeout)
                status_code = resp.status_code
                content_type = resp.headers.get("Content-Type", "").strip().lower()
                length_header = resp.headers.get("Content-Length", "").strip()

            if status_code >= 400:
                raise InstagramConnectionError(
                    f"Remote media server returned HTTP status error {status_code} for URL: '{url}'"
                )

            if length_header.isdigit():
                size_bytes = int(length_header)

        except requests.Timeout as e:
            raise InstagramTimeoutError(f"HTTP request timed out after {self.timeout}s for URL: '{url}'")
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
