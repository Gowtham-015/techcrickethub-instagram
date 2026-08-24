import os
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse


@dataclass
class MediaAsset:
    """Dataclass holding extracted metadata for remote media assets."""

    media_type: str
    url: str
    content_type: Optional[str] = None
    extension: Optional[str] = None
    source_host: Optional[str] = None
    is_https: bool = True
    size_bytes: Optional[int] = None
    status_code: Optional[int] = None

    @classmethod
    def from_url(
        cls,
        url: str,
        media_type: str,
        content_type: Optional[str] = None,
        size_bytes: Optional[int] = None,
        status_code: Optional[int] = None,
    ) -> "MediaAsset":
        """Constructs a MediaAsset instance from a URL and optional HTTP headers."""
        parsed = urlparse(url or "")
        source_host = parsed.netloc.lower()
        is_https = parsed.scheme.lower() == "https"

        path = parsed.path
        ext = os.path.splitext(path)[1].lower() if path else ""

        return cls(
            media_type=media_type.upper(),
            url=url,
            content_type=content_type,
            extension=ext if ext else None,
            source_host=source_host if source_host else None,
            is_https=is_https,
            size_bytes=size_bytes,
            status_code=status_code,
        )
