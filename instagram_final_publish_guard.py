import hashlib
import json
import logging
import os
import re
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config import Config
from instagram_content_bundle import ContentBundle
from instagram_repetition_guard import InstagramRepetitionGuard
from security import redact_url

logger = logging.getLogger("InstagramFinalPublishGuard")


@dataclass
class GuardResult:
    """Represents outcome of final pre-publish duplicate & integrity evaluation."""

    is_valid: bool
    error_code: str  # SUCCESS, DUPLICATE_SOURCE, DUPLICATE_CONTENT_ID, DUPLICATE_TITLE, DUPLICATE_FINGERPRINT, DUPLICATE_MEDIA, DUPLICATE_CAPTION, DUPLICATE_MEDIA_URL, CAPTION_MISMATCH
    message: str
    bundle: Optional[ContentBundle] = None


class InstagramFinalPublishGuard:
    """Final Pre-Publish Safety & Reliability Guard executing multi-layer duplicate checks

    and caption/content integrity verification immediately before Meta Graph API publishing.
    """

    def __init__(self, config: Optional[Config] = None, data_dir: Optional[str] = None):
        self.config = config or Config.load_from_env(validate=False)
        self.data_dir = data_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        os.makedirs(self.data_dir, exist_ok=True)

        self.published_history_file = os.path.join(self.data_dir, "instagram_published_history.json")
        self.media_history_file = os.path.join(self.data_dir, "instagram_media_history.json")
        self.repetition_guard = InstagramRepetitionGuard(
            similarity_threshold=self.config.final_title_similarity_threshold
        )

        self._ensure_history_files()

    def _ensure_history_files(self) -> None:
        if not os.path.exists(self.published_history_file):
            with open(self.published_history_file, "w", encoding="utf-8") as f:
                json.dump({"items": []}, f, indent=2)
        if not os.path.exists(self.media_history_file):
            with open(self.media_history_file, "w", encoding="utf-8") as f:
                json.dump({"hashes": [], "urls": [], "graphic_hashes": []}, f, indent=2)

    def canonicalize_url(self, url: str) -> str:
        """Normalizes canonical source URL by stripping tracking query params, trailing slashes, and lowercase host."""
        if not url:
            return ""
        try:
            parsed = urllib.parse.urlparse(url.strip())
            host = parsed.netloc.lower()
            if host.startswith("www."):
                host = host[4:]
            path = parsed.path.rstrip("/")

            # Filter out tracking query params
            query_pairs = urllib.parse.parse_qsl(parsed.query)
            clean_pairs = [
                (k, v)
                for k, v in query_pairs
                if not (
                    k.startswith("utm_")
                    or k in ("fbclid", "gclid", "ref", "source", "rss", "mc_cid", "mc_eid")
                )
            ]
            clean_query = urllib.parse.urlencode(sorted(clean_pairs))

            scheme = parsed.scheme.lower() or "https"
            return urllib.parse.urlunparse((scheme, host, path, "", clean_query, ""))
        except Exception:
            return url.strip().lower().rstrip("/")

    def normalize_text(self, text: str) -> str:
        """Normalizes text for string matching: lowercase, strip punctuation and whitespace."""
        if not text:
            return ""
        s = text.lower()
        s = re.sub(r"[^\w\s]", "", s)
        return " ".join(s.split())

    def calculate_sha256(self, data: str | bytes) -> str:
        """Calculates SHA256 hex string."""
        if isinstance(data, str):
            data = data.encode("utf-8")
        return hashlib.sha256(data).hexdigest()

    def calculate_fact_fingerprint(self, title: str, summary: str, facts: Optional[List[str]] = None) -> str:
        """Creates a deterministic content fingerprint from title, summary, and facts."""
        norm_t = self.normalize_text(title)
        norm_s = self.normalize_text(summary)
        norm_f = " ".join([self.normalize_text(f) for f in (facts or [])])
        combined = f"{norm_t}|{norm_s}|{norm_f}"
        return self.calculate_sha256(combined)

    def get_published_history(self) -> List[Dict[str, Any]]:
        """Loads permanent published history from disk."""
        self._ensure_history_files()
        try:
            with open(self.published_history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("items", [])
        except Exception as e:
            logger.error(f"Failed to load published history: {e}")
            return []

    def get_media_hashes(self) -> set[str]:
        """Loads media hashes from disk."""
        self._ensure_history_files()
        try:
            with open(self.media_history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data.get("hashes", []))
        except Exception:
            return set()

    def get_graphic_hashes(self) -> set[str]:
        """Loads generated graphic hashes from disk."""
        self._ensure_history_files()
        try:
            with open(self.media_history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data.get("graphic_hashes", []))
        except Exception:
            return set()

    def check_caption_integrity(self, bundle: ContentBundle) -> bool:
        """Verifies that the caption actually describes the content item's title/summary."""
        if not bundle.caption or not bundle.caption.strip():
            return True  # Pipeline auto-generates caption if empty

        norm_caption = self.normalize_text(bundle.caption)
        norm_title = self.normalize_text(bundle.title)

        if not norm_title or not norm_caption:
            return True

        if norm_title in norm_caption or norm_caption in norm_title:
            return True

        # Extract major words (length >= 4) from title
        title_words = [w for w in norm_title.split() if len(w) >= 4]
        if len(title_words) <= 1:
            return True

        matching_words = [w for w in title_words if w in norm_caption]
        # At least 1 major entity/keyword from title must be in caption
        return len(matching_words) > 0

    def verify_and_guard(
        self,
        bundle: ContentBundle,
        media_bytes: Optional[bytes] = None,
    ) -> GuardResult:
        """Executes multi-layer pre-publish duplicate & integrity checks immediately before publishing."""
        if not getattr(self.config, "final_publish_guard_enabled", True):
            return GuardResult(is_valid=True, error_code="SUCCESS", message="Guard disabled.", bundle=bundle)

        # 0. Sample / Fake Video URL Rejection
        if bundle.media_type == "REEL" and bundle.media_url:
            lowered_media = bundle.media_url.lower()
            if "ai_commentary.mp4" in lowered_media or "sample" in lowered_media or "test_video" in lowered_media:
                return GuardResult(
                    is_valid=False,
                    error_code="INVALID_MEDIA",
                    message=f"Sample / fake video URL '{redact_url(bundle.media_url)}' barred from live Reel publishing.",
                    bundle=bundle,
                )

        # 0b. Media Rights Validation
        allowed_rights = {
            "OWNED",
            "LICENSED",
            "AUTHORIZED",
            "PUBLIC_DOMAIN",
            "CC_LICENSE_ALLOWED",
            "USER_PROVIDED_WITH_PERMISSION",
            "ORIGINAL_GENERATED",
        }
        rights_status = (getattr(bundle, "media_rights_status", "UNKNOWN") or "UNKNOWN").strip().upper()
        if rights_status not in allowed_rights:
            return GuardResult(
                is_valid=False,
                error_code="MEDIA_RIGHTS_UNKNOWN" if rights_status == "UNKNOWN" else "MEDIA_RIGHTS_RESTRICTED",
                message=f"Media rights status '{rights_status}' is unallowed for live publishing.",
                bundle=bundle,
            )

        published_items = self.get_published_history()

        # 1. Canonical Source URL Check
        canon_url = self.canonicalize_url(bundle.source_url)
        canon_hash = self.calculate_sha256(canon_url) if canon_url else ""
        if canon_hash:
            for item in published_items:
                if item.get("source_hash") == canon_hash or (
                    item.get("canonical_source_url") and self.canonicalize_url(item["canonical_source_url"]) == canon_url
                ):
                    return GuardResult(
                        is_valid=False,
                        error_code="DUPLICATE_SOURCE",
                        message=f"Canonical source URL '{redact_url(canon_url)}' was already published.",
                        bundle=bundle,
                    )

        # 2. Content ID Check
        if bundle.content_id:
            for item in published_items:
                if item.get("content_id") == bundle.content_id:
                    return GuardResult(
                        is_valid=False,
                        error_code="DUPLICATE_CONTENT_ID",
                        message=f"Content ID '{bundle.content_id}' was already published.",
                        bundle=bundle,
                    )

        # 3. Exact Normalized Title Check
        norm_title = self.normalize_text(bundle.title)
        title_hash = self.calculate_sha256(norm_title) if norm_title else ""
        if norm_title:
            for item in published_items:
                pub_norm_title = self.normalize_text(item.get("title", ""))
                if pub_norm_title and pub_norm_title == norm_title:
                    return GuardResult(
                        is_valid=False,
                        error_code="DUPLICATE_TITLE",
                        message=f"Exact normalized title '{bundle.title}' was already published.",
                        bundle=bundle,
                    )

        # 4. Near-Duplicate Title Check (Similarity >= 0.65)
        if bundle.title:
            for item in published_items:
                pub_title = item.get("title", "")
                if pub_title:
                    sim = self.repetition_guard.calculate_similarity(bundle.title, pub_title)
                    if sim >= self.config.final_title_similarity_threshold:
                        return GuardResult(
                            is_valid=False,
                            error_code="DUPLICATE_TITLE",
                            message=f"Near-duplicate title detected (similarity {sim}): '{bundle.title}' vs published '{pub_title}'.",
                            bundle=bundle,
                        )

        # 5. Summary / Fact Fingerprint Check
        fingerprint = self.calculate_fact_fingerprint(bundle.title, bundle.summary, bundle.hashtags)
        for item in published_items:
            if item.get("content_hash") == fingerprint:
                return GuardResult(
                    is_valid=False,
                    error_code="DUPLICATE_FINGERPRINT",
                    message=f"Fact fingerprint '{fingerprint[:12]}' matched a previously published story.",
                    bundle=bundle,
                )

        # 6. Media Bytes SHA256 Check
        if media_bytes:
            media_hash = self.calculate_sha256(media_bytes)
            recorded_hashes = self.get_media_hashes()
            if media_hash in recorded_hashes:
                return GuardResult(
                    is_valid=False,
                    error_code="DUPLICATE_MEDIA",
                    message=f"Exact media byte SHA256 '{media_hash[:12]}' was already published.",
                    bundle=bundle,
                )
            for item in published_items:
                if item.get("media_hash") == media_hash:
                    return GuardResult(
                        is_valid=False,
                        error_code="DUPLICATE_MEDIA",
                        message=f"Media hash '{media_hash[:12]}' matched published history record.",
                        bundle=bundle,
                    )

        # 7. Generated Graphic Deduplication
        graphic_hash = self.calculate_sha256(f"graphic:{norm_title}")
        graphic_recorded = self.get_graphic_hashes()
        if graphic_hash in graphic_recorded:
            return GuardResult(
                is_valid=False,
                error_code="DUPLICATE_MEDIA",
                message=f"Generated graphic card for '{bundle.title[:30]}' was already published.",
                bundle=bundle,
            )

        # 8. Media URL Comparison
        if bundle.media_url and "maxresdefault.jpg" not in bundle.media_url:
            norm_media_url = self.canonicalize_url(bundle.media_url)
            for item in published_items:
                pub_media = item.get("media_url", "")
                if pub_media and "maxresdefault.jpg" not in pub_media:
                    if self.canonicalize_url(pub_media) == norm_media_url or pub_media.strip() == bundle.media_url.strip():
                        return GuardResult(
                            is_valid=False,
                            error_code="DUPLICATE_MEDIA_URL",
                            message=f"Media URL '{redact_url(norm_media_url)}' was already published.",
                            bundle=bundle,
                        )

        # 9. Caption Integrity Check
        if not self.check_caption_integrity(bundle):
            return GuardResult(
                is_valid=False,
                error_code="CAPTION_MISMATCH",
                message=f"Caption integrity check failed: caption does not describe title '{bundle.title[:30]}'.",
                bundle=bundle,
            )

        bundle.verification_status = "VERIFIED"
        return GuardResult(is_valid=True, error_code="SUCCESS", message="Final Publish Guard passed cleanly.", bundle=bundle)

    def record_published_item(
        self,
        bundle: ContentBundle,
        media_id: str,
        permalink: str = "",
        media_bytes: Optional[bytes] = None,
    ) -> None:
        """Atomically appends a published record to instagram_published_history.json and instagram_media_history.json."""
        self._ensure_history_files()
        canon_url = self.canonicalize_url(bundle.source_url)
        canon_hash = self.calculate_sha256(canon_url) if canon_url else ""
        norm_title = self.normalize_text(bundle.title)
        title_hash = self.calculate_sha256(norm_title) if norm_title else ""
        fingerprint = self.calculate_fact_fingerprint(bundle.title, bundle.summary, bundle.hashtags)
        norm_caption = self.normalize_text(bundle.caption)
        caption_hash = self.calculate_sha256(norm_caption) if norm_caption else ""
        graphic_hash = self.calculate_sha256(f"graphic:{norm_title}")

        m_hash = bundle.media_hash
        if media_bytes:
            m_hash = self.calculate_sha256(media_bytes)

        record = {
            "instagram_media_id": media_id,
            "content_id": bundle.content_id,
            "canonical_source_url": canon_url,
            "source_hash": canon_hash,
            "title": bundle.title,
            "normalized_title": norm_title,
            "title_hash": title_hash,
            "content_hash": fingerprint,
            "media_hash": m_hash,
            "media_url": bundle.media_url,
            "caption_hash": caption_hash,
            "category": bundle.category,
            "media_type": bundle.media_type,
            "published_at": datetime.now(timezone.utc).isoformat(),
            "instagram_permalink": permalink,
            "status": "PUBLISHED",
        }

        # Atomic write for published history
        items = self.get_published_history()
        items.append(record)
        temp_file = f"{self.published_history_file}.tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump({"items": items}, f, indent=2)
        os.replace(temp_file, self.published_history_file)

        # Update media history
        try:
            with open(self.media_history_file, "r", encoding="utf-8") as f:
                m_data = json.load(f)
            hashes = set(m_data.get("hashes", []))
            urls = set(m_data.get("urls", []))
            g_hashes = set(m_data.get("graphic_hashes", []))

            if m_hash:
                hashes.add(m_hash)
            if bundle.media_url:
                urls.add(bundle.media_url)
            g_hashes.add(graphic_hash)

            m_temp = f"{self.media_history_file}.tmp"
            with open(m_temp, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "hashes": list(hashes),
                        "urls": list(urls),
                        "graphic_hashes": list(g_hashes),
                    },
                    f,
                    indent=2,
                )
            os.replace(m_temp, self.media_history_file)
        except Exception as e:
            logger.error(f"Failed to update media history file: {e}")
