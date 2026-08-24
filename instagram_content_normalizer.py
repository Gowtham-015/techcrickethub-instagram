import re
from typing import TYPE_CHECKING, Any, Dict, Optional
from exceptions import InstagramConfigError

if TYPE_CHECKING:
    from instagram_pipeline import InstagramContent


class InstagramContentNormalizer:
    """Normalizes raw dictionary content items into structured InstagramContent models."""

    VALID_MEDIA_TYPES = {"IMAGE", "REEL"}

    @classmethod
    def normalize(cls, raw: Dict[str, Any]) -> "InstagramContent":
        """Normalizes raw input dictionary into InstagramContent."""
        from instagram_pipeline import InstagramContent

        if not raw or not isinstance(raw, dict):
            raise InstagramConfigError("Content item must be a non-empty dictionary.")

        raw_id = str(raw.get("id") or "").strip()
        raw_title = str(raw.get("title") or "").strip()
        raw_summary = str(raw.get("summary") or "").strip()
        raw_category = str(raw.get("category") or "cricket").strip().lower()
        raw_source = str(raw.get("source") or "").strip() or None
        raw_image_url = str(raw.get("image_url") or "").strip() or None
        raw_video_url = str(raw.get("video_url") or "").strip() or None
        raw_caption = str(raw.get("caption") or "").strip() or None
        raw_media_type = str(raw.get("media_type") or "IMAGE").strip().upper()

        raw_hashtags = raw.get("hashtags")
        hashtags = raw_hashtags if isinstance(raw_hashtags, list) else None

        clean_title = re.sub(r"\s+", " ", raw_title)
        clean_summary = re.sub(r"\s+", " ", raw_summary)

        if not clean_title and not clean_summary and not raw_caption:
            raise InstagramConfigError("Content item must contain a non-empty title, summary, or caption.")

        if raw_media_type not in cls.VALID_MEDIA_TYPES:
            raise InstagramConfigError(
                f"Invalid media_type: '{raw_media_type}'. Must be one of {sorted(list(cls.VALID_MEDIA_TYPES))}."
            )

        if raw_media_type == "IMAGE" and not raw_image_url:
            raise InstagramConfigError("IMAGE content type requires a valid image_url.")

        if raw_media_type == "REEL" and not raw_video_url:
            raise InstagramConfigError("REEL content type requires a valid video_url.")

        metadata = raw.get("metadata")
        clean_metadata = metadata if isinstance(metadata, dict) else {}
        if raw_id:
            clean_metadata["content_id"] = raw_id

        return InstagramContent(
            title=clean_title,
            summary=clean_summary,
            category=raw_category,
            source=raw_source,
            image_url=raw_image_url,
            video_url=raw_video_url,
            caption=raw_caption,
            hashtags=hashtags,
            media_type=raw_media_type,
            metadata=clean_metadata,
        )
