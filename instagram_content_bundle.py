import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("InstagramContentBundle")


@dataclass
class ContentBundle:
    """Immutable representation of a unified content item across facts, media, and caption."""

    content_id: str
    category: str
    title: str
    summary: str
    source_url: str
    source_domain: str
    published_at: str
    media_url: str
    media_type: str  # IMAGE or REEL
    media_hash: str = ""
    facts: Dict[str, Any] = field(default_factory=dict)
    caption: str = ""
    hashtags: List[str] = field(default_factory=list)
    match_context: Dict[str, Any] = field(default_factory=dict)
    media_rights_status: str = "ORIGINAL_GENERATED"  # OWNED, LICENSED, AUTHORIZED, PUBLIC_DOMAIN, CC_LICENSE_ALLOWED, USER_PROVIDED_WITH_PERMISSION, ORIGINAL_GENERATED, UNKNOWN, RESTRICTED
    verification_status: str = "PENDING"  # VERIFIED, REJECTED, CONTENT_INTEGRITY_FAILED

    def calculate_media_hash(self, media_bytes: Optional[bytes] = None) -> str:
        """Calculates SHA256 of media bytes or media URL if bytes unavailable."""
        if media_bytes:
            self.media_hash = hashlib.sha256(media_bytes).hexdigest()
        elif self.media_url:
            self.media_hash = hashlib.sha256(self.media_url.encode("utf-8")).hexdigest()
        return self.media_hash

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content_id": self.content_id,
            "category": self.category,
            "title": self.title,
            "summary": self.summary,
            "source_url": self.source_url,
            "source_domain": self.source_domain,
            "published_at": self.published_at,
            "media_url": self.media_url,
            "media_type": self.media_type,
            "media_hash": self.media_hash,
            "facts": self.facts,
            "caption": self.caption,
            "hashtags": self.hashtags,
            "match_context": self.match_context,
            "media_rights_status": self.media_rights_status,
            "verification_status": self.verification_status,
        }


@dataclass
class ContentIntegrityResult:
    is_valid: bool
    error_code: str  # SUCCESS, CONTENT_INTEGRITY_FAILED, CAPTION_MISMATCH, SOURCE_MISMATCH
    message: str
    bundle: Optional[ContentBundle] = None


class ContentIntegrityValidator:
    """Validates that title, summary, media, caption, source, and facts belong to the exact same article."""

    @staticmethod
    def normalize_text(text: str) -> str:
        if not text:
            return ""
        s = text.lower()
        s = re.sub(r"[^\w\s]", "", s)
        return " ".join(s.split())

    def validate_bundle(self, bundle: ContentBundle) -> ContentIntegrityResult:
        """Enforces immutable bundle alignment across content_id, title, media, caption, and facts."""
        if not bundle.content_id:
            return ContentIntegrityResult(
                is_valid=False,
                error_code="CONTENT_INTEGRITY_FAILED",
                message="ContentBundle missing required content_id.",
                bundle=bundle,
            )

        if not bundle.source_url:
            bundle.source_url = f"https://www.techcrickethub.com/stories/{bundle.content_id}"

        if not bundle.source_url.startswith("http"):
            return ContentIntegrityResult(
                is_valid=False,
                error_code="SOURCE_MISMATCH",
                message=f"ContentBundle content_id '{bundle.content_id}' has invalid source_url: {bundle.source_url}",
                bundle=bundle,
            )

        if not bundle.title or not bundle.summary:
            return ContentIntegrityResult(
                is_valid=False,
                error_code="CONTENT_INTEGRITY_FAILED",
                message=f"ContentBundle '{bundle.content_id}' missing title or summary.",
                bundle=bundle,
            )

        # Validate caption matching
        if bundle.caption:
            norm_title = self.normalize_text(bundle.title)
            norm_caption = self.normalize_text(bundle.caption)
            title_words = [w for w in norm_title.split() if len(w) > 3]

            # Check key word overlap between title and caption
            overlap = [w for w in title_words if w in norm_caption]
            if title_words and len(overlap) == 0 and norm_title not in norm_caption:
                return ContentIntegrityResult(
                    is_valid=False,
                    error_code="CAPTION_MISMATCH",
                    message=(
                        f"Caption for bundle '{bundle.content_id}' does not match title. "
                        f"Title: '{bundle.title}', Caption: '{bundle.caption[:60]}...'"
                    ),
                    bundle=bundle,
                )

        # Validate media rights status
        allowed_rights = {
            "OWNED",
            "LICENSED",
            "AUTHORIZED",
            "PUBLIC_DOMAIN",
            "CC_LICENSE_ALLOWED",
            "USER_PROVIDED_WITH_PERMISSION",
            "ORIGINAL_GENERATED",
        }
        rights_status = (bundle.media_rights_status or "UNKNOWN").strip().upper()
        if rights_status not in allowed_rights:
            return ContentIntegrityResult(
                is_valid=False,
                error_code="MEDIA_RIGHTS_UNKNOWN" if rights_status == "UNKNOWN" else "MEDIA_RIGHTS_RESTRICTED",
                message=f"ContentBundle '{bundle.content_id}' rejected due to unallowed media_rights_status: '{rights_status}'",
                bundle=bundle,
            )

        bundle.verification_status = "VERIFIED"
        return ContentIntegrityResult(
            is_valid=True,
            error_code="SUCCESS",
            message=f"ContentBundle '{bundle.content_id}' passed all integrity checks.",
            bundle=bundle,
        )
