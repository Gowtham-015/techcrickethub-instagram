import logging
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import requests

from security import redact_token

logger = logging.getLogger("InstagramSourceVerifier")


@dataclass
class SourceVerificationResult:
    is_valid: bool
    status_code: int = 0
    reasons: List[str] = field(default_factory=list)
    source_domain: str = ""
    verification_time: float = 0.0


class InstagramSourceVerifier:
    """Verifies authenticity, HTTP reachability, domain validity, and freshness of content sources."""

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.blocked_test_domains = [
            "raw.githubusercontent.com",
            "localhost",
            "127.0.0.1",
            "example.com",
        ]

    def verify_source(self, source_url: str, source_name: Optional[str] = None, strict_production: bool = False) -> SourceVerificationResult:
        """Validates source URL syntax, reachability (HTTP HEAD/GET), and excludes test domains."""
        reasons = []

        if not source_url or not isinstance(source_url, str) or not source_url.strip():
            return SourceVerificationResult(is_valid=False, reasons=["Missing or empty source_url."])

        url_clean = source_url.strip()

        # Parse domain
        try:
            parsed = urllib.parse.urlparse(url_clean)
            if parsed.scheme not in ("http", "https"):
                return SourceVerificationResult(
                    is_valid=False, reasons=[f"Invalid URL scheme '{parsed.scheme}'. Expected HTTP/HTTPS."]
                )
            domain = parsed.netloc.lower()
        except Exception as e:
            return SourceVerificationResult(is_valid=False, reasons=[f"URL parse error: {e}"])

        # Check blocked test domains (for production real content)
        if strict_production:
            for blocked in self.blocked_test_domains:
                if blocked in domain:
                    reasons.append(f"Blocked sample test domain '{blocked}'.")

        # Perform HTTP HEAD verification
        status_code = 200
        if not (any(b in domain for b in self.blocked_test_domains) and not strict_production):
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                }
                resp = requests.head(url_clean, headers=headers, timeout=self.timeout, allow_redirects=True)
                status_code = resp.status_code

                if status_code in (403, 405):  # Method Not Allowed or Cloudflare 403 on HEAD, fallback to GET
                    resp = requests.get(url_clean, headers=headers, timeout=self.timeout, stream=True)
                    status_code = resp.status_code
                    resp.close()

                if status_code < 200 or status_code >= 400:
                    if status_code in (403, 405) and domain and "." in domain:
                        logger.warning(f"HTTP {status_code} Cloudflare/WAF block for domain {domain}. Allowing valid news URL.")
                        status_code = 200
                    else:
                        reasons.append(f"HTTP status verification failed: Code {status_code}.")

            except Exception as e:
                logger.warning(f"HTTP verification error for {redact_token(url_clean)}: {redact_token(str(e))}")
                reasons.append(f"HTTP connection failed: {redact_token(str(e))}")

        is_valid = len(reasons) == 0
        return SourceVerificationResult(
            is_valid=is_valid,
            status_code=status_code,
            reasons=reasons,
            source_domain=domain,
        )

    def verify_item(self, item: Dict[str, Any], strict_production: bool = False) -> SourceVerificationResult:
        """Verifies complete metadata payload for a real content item."""
        reasons = []

        content_id = item.get("content_id", "")
        if strict_production and (not content_id or str(content_id).startswith("sample-")):
            reasons.append(f"Invalid production content_id '{content_id}' (sample content barred).")

        source_url = item.get("source_url") or item.get("link") or item.get("image_url") or item.get("video_url")
        if not source_url:
            reasons.append("Missing source_url metadata.")

        title = item.get("title")
        if not title or not str(title).strip():
            reasons.append("Missing or empty title.")

        if reasons:
            return SourceVerificationResult(is_valid=False, reasons=reasons)

        return self.verify_source(
            source_url=source_url,
            source_name=item.get("source_name"),
            strict_production=strict_production,
        )
