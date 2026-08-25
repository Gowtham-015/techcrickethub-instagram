import hashlib
import json
import logging
import os
import re
import urllib.parse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config import Config
from instagram_content_bundle import ContentBundle
from instagram_repetition_guard import InstagramRepetitionGuard
from security import redact_url

logger = logging.getLogger("InstagramFinalDuplicateGate")


@dataclass
class GateResult:
    """Represents outcome of final pre-publish duplicate evaluation."""

    is_valid: bool
    error_code: str  # SUCCESS, DUPLICATE_SOURCE, DUPLICATE_CONTENT_ID, DUPLICATE_TITLE, DUPLICATE_MEDIA, DUPLICATE_CAPTION, DUPLICATE_MEDIA_URL
    message: str
    bundle: Optional[ContentBundle] = None


class InstagramFinalDuplicateGate:
    """Final Pre-Publish Duplicate Gate performing 8 independent duplicate checks

    immediately before calling Meta Graph API container creation / publishing endpoints.
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
                json.dump({"hashes": [], "urls": []}, f, indent=2)

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

    def check_final_duplicate(
        self,
        bundle: ContentBundle,
        media_bytes: Optional[bytes] = None,
    ) -> GateResult:
        """Executes 8 independent duplicate checks against persistent published history."""
        if not self.config.final_duplicate_gate_enabled:
            return GateResult(is_valid=True, error_code="SUCCESS", message="Gate disabled.", bundle=bundle)

        published_items = self.get_published_history()

        # 1. Canonical Source URL Check
        canon_url = self.canonicalize_url(bundle.source_url)
        canon_hash = self.calculate_sha256(canon_url) if canon_url else ""
        if canon_hash:
            for item in published_items:
                if item.get("source_hash") == canon_hash or (
                    item.get("canonical_source_url") and self.canonicalize_url(item["canonical_source_url"]) == canon_url
                ):
                    return GateResult(
                        is_valid=False,
                        error_code="DUPLICATE_SOURCE",
                        message=f"Canonical source URL '{redact_url(canon_url)}' was already published.",
                        bundle=bundle,
                    )

        # 2. Content ID Check
        if bundle.content_id:
            for item in published_items:
                if item.get("content_id") == bundle.content_id:
                    return GateResult(
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
                    return GateResult(
                        is_valid=False,
                        error_code="DUPLICATE_TITLE",
                        message=f"Exact normalized title '{bundle.title}' was already published.",
                        bundle=bundle,
                    )

        # 4. Near-Duplicate Title Check
        if bundle.title:
            for item in published_items:
                pub_title = item.get("title", "")
                if pub_title:
                    sim = self.repetition_guard.calculate_similarity(bundle.title, pub_title)
                    if sim >= self.config.final_title_similarity_threshold:
                        return GateResult(
                            is_valid=False,
                            error_code="DUPLICATE_TITLE",
                            message=f"Near-duplicate title detected (similarity {sim}): '{bundle.title}' vs published '{pub_title}'.",
                            bundle=bundle,
                        )

        # 5. Media Bytes SHA256 Check
        if media_bytes:
            media_hash = self.calculate_sha256(media_bytes)
            recorded_hashes = self.get_media_hashes()
            if media_hash in recorded_hashes:
                return GateResult(
                    is_valid=False,
                    error_code="DUPLICATE_MEDIA",
                    message=f"Exact media byte SHA256 '{media_hash[:12]}' was already published.",
                    bundle=bundle,
                )
            for item in published_items:
                if item.get("media_hash") == media_hash:
                    return GateResult(
                        is_valid=False,
                        error_code="DUPLICATE_MEDIA",
                        message=f"Media hash '{media_hash[:12]}' matched published history record.",
                        bundle=bundle,
                    )

        # 6. Media URL Comparison
        if bundle.media_url and "maxresdefault.jpg" not in bundle.media_url:
            norm_media_url = self.canonicalize_url(bundle.media_url)
            for item in published_items:
                pub_media = item.get("media_url", "")
                if pub_media and "maxresdefault.jpg" not in pub_media:
                    if self.canonicalize_url(pub_media) == norm_media_url:
                        return GateResult(
                            is_valid=False,
                            error_code="DUPLICATE_MEDIA_URL",
                            message=f"Media URL '{redact_url(norm_media_url)}' was already published.",
                            bundle=bundle,
                        )

        # 7. Caption Fingerprint Check
        norm_caption = self.normalize_text(bundle.caption)
        caption_hash = self.calculate_sha256(norm_caption) if norm_caption else ""
        if caption_hash:
            for item in published_items:
                if item.get("caption_hash") == caption_hash:
                    return GateResult(
                        is_valid=False,
                        error_code="DUPLICATE_CAPTION",
                        message=f"Caption fingerprint '{caption_hash[:12]}' was already published.",
                        bundle=bundle,
                    )

        bundle.verification_status = "VERIFIED"
        return GateResult(is_valid=True, error_code="SUCCESS", message="Final Duplicate Gate passed cleanly.", bundle=bundle)

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
        norm_caption = self.normalize_text(bundle.caption)
        caption_hash = self.calculate_sha256(norm_caption) if norm_caption else ""

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
            "media_hash": m_hash,
            "media_url": bundle.media_url,
            "caption_hash": caption_hash,
            "category": bundle.category,
            "media_type": bundle.media_type,
            "published_at": datetime.now(timezone.utc).isoformat(),
            "instagram_permalink": permalink,
        }

        # Atomic write for published history
        items = self.get_published_history()
        items.append(record)
        temp_file = f"{self.published_history_file}.tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump({"items": items}, f, indent=2)
        os.replace(temp_file, self.published_history_file)

        # Update media history
        if m_hash or bundle.media_url:
            try:
                with open(self.media_history_file, "r", encoding="utf-8") as f:
                    m_data = json.load(f)
                hashes = set(m_data.get("hashes", []))
                urls = set(m_data.get("urls", []))
                if m_hash:
                    hashes.add(m_hash)
                if bundle.media_url:
                    urls.add(bundle.media_url)

                m_temp = f"{self.media_history_file}.tmp"
                with open(m_temp, "w", encoding="utf-8") as f:
                    json.dump({"hashes": list(hashes), "urls": list(urls)}, f, indent=2)
                os.replace(m_temp, self.media_history_file)
            except Exception as e:
                logger.error(f"Failed to update media history file: {e}")
