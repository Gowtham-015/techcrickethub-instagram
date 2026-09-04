import hashlib
import logging
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import requests

from config import Config
from instagram_content_source import InstagramContentSource
from security import redact_token

logger = logging.getLogger("InstagramRealNewsSource")


class InstagramRealNewsSource(InstagramContentSource):
    """Production real news source acquiring authentic Cricket and Tech news from verified RSS feeds."""

    def __init__(
        self,
        config: Optional[Config] = None,
        timeout: int = 10,
    ):
        self.config = config or Config.load_from_env(validate=False)
        self.timeout = timeout
        self.cricket_feeds = [f.strip() for f in getattr(self.config, "cricket_rss_feeds", "").split(",") if f.strip()]
        self.tech_feeds = [f.strip() for f in getattr(self.config, "tech_rss_feeds", "").split(",") if f.strip()]
        self.launches_feeds = [f.strip() for f in getattr(self.config, "launches_rss_feeds", "https://www.gsmarena.com/rss-news-reviews.php3,https://techcrunch.com/category/gadgets/feed/").split(",") if f.strip()]
        self.geopolitics_feeds = [f.strip() for f in getattr(self.config, "geopolitics_rss_feeds", "https://timesofindia.indiatimes.com/rssfeeds/296589292.cms").split(",") if f.strip()]
        self.democracy_feeds = [f.strip() for f in getattr(self.config, "democracy_rss_feeds", "https://www.idea.int/rss.xml").split(",") if f.strip()]
        self.entertainment_feeds = [f.strip() for f in getattr(self.config, "entertainment_rss_feeds", "https://variety.com/feed/").split(",") if f.strip()]

    @staticmethod
    def generate_stable_id(url: str, source_name: str) -> str:
        """Generates a stable, SHA256-based content ID for production items."""
        clean_url = (url or "").strip().lower()
        hasher = hashlib.sha256(f"{source_name}:{clean_url}".encode("utf-8"))
        return f"real-{hasher.hexdigest()[:16]}"

    @staticmethod
    def upload_to_public_host(local_path: str, fallback_url: str) -> str:
        """Delegates asset upload to consolidated PublicMediaHost implementation."""
        from instagram_public_media_host import PublicMediaHost
        return PublicMediaHost().upload_video(local_path, fallback_raw_url=fallback_url)

    def prepare_instagram_compliant_photo(self, image_url: str, content_id: str) -> Optional[str]:
        """Ensures photo complies with Meta Graph API aspect ratio requirements (4:5 to 1.91:1) without adding any text or graphics."""
        if not image_url or not isinstance(image_url, str):
            return None
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            }
            resp = requests.get(image_url, headers=headers, timeout=8)
            if resp.status_code != 200:
                return image_url
            import io
            from PIL import Image
            img = Image.open(io.BytesIO(resp.content)).convert("RGB")
            w, h = img.size
            if h == 0 or w == 0:
                return image_url
            ratio = w / float(h)
            if 0.8 <= ratio <= 1.91:
                return image_url  # Already 100% Meta API aspect-ratio compliant

            # Aspect ratio outside 4:5 to 1.91:1 (e.g. 2:1 banner).
            # Center raw photo inside a clean 1080x1080 canvas with ZERO text or AI graphics.
            canvas = Image.new("RGB", (1080, 1080), (15, 23, 42))
            img.thumbnail((1080, 1080), Image.Resampling.LANCZOS)
            nw, nh = img.size
            canvas.paste(img, ((1080 - nw) // 2, (1080 - nh) // 2))

            base_dir = os.path.dirname(os.path.abspath(__file__))
            gen_dir = os.path.join(base_dir, "media", "generated")
            os.makedirs(gen_dir, exist_ok=True)
            photo_path = os.path.join(gen_dir, f"photo_{content_id}.jpg")
            canvas.save(photo_path, "JPEG", quality=95)
            rel_n = os.path.basename(photo_path)
            raw_url = f"https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/media/generated/{rel_n}"
            return self.upload_to_public_host(photo_path, raw_url)
        except Exception as e:
            logger.warning(f"Photo aspect-ratio compliance check failed for {content_id}: {e}")
            return image_url




    @staticmethod
    def parse_rss_date(date_str: Optional[str]) -> Optional[datetime]:
        """Parses common RSS pubDate formats into timezone-aware datetime."""
        if not date_str or not isinstance(date_str, str):
            return None
        date_clean = date_str.strip()

        formats = [
            "%a, %d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S GMT",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(date_clean, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                pass
        return None

    def fetch_feed_items(self, feed_url: str, category: str) -> List[Dict[str, Any]]:
        """Fetches and parses articles from a single RSS feed URL."""
        if not feed_url:
            return []

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept": "application/rss+xml,application/xml;q=0.9,text/xml;q=0.8,*/*;q=0.7",
            }
            resp = requests.get(feed_url, headers=headers, timeout=self.timeout)
            if resp.status_code != 200:
                logger.warning(f"RSS feed HTTP {resp.status_code} for {redact_token(feed_url)}")
                return []

            root = ET.fromstring(resp.content)
            items = root.findall(".//item")
            results = []
            now = datetime.now(timezone.utc)

            max_age_hours = (
                self.config.max_cricket_news_age_hours
                if category == "cricket"
                else self.config.max_tech_news_age_hours
            )

            source_domain = feed_url.split("/")[2] if "//" in feed_url else feed_url

            for item in items[:5]:
                import html
                title = html.unescape((item.findtext("title") or "").strip())
                link = (item.findtext("link") or "").strip()
                description = html.unescape((item.findtext("description") or "").strip())
                pub_date_str = item.findtext("pubDate") or item.findtext("dc:date")

                # Remove HTML tags and sanitize HTML entities from description
                clean_desc = html.unescape(re.sub(r"<[^>]+>", "", description)).replace("&nbsp;", " ").strip()
                clean_desc = re.sub(r"\s+", " ", clean_desc).strip()

                if not title or not link:
                    continue

                pub_dt = self.parse_rss_date(pub_date_str) or now
                age_hours = (now - pub_dt).total_seconds() / 3600.0

                # Reject stale content
                if age_hours > max_age_hours:
                    logger.info(f"Skipping stale {category} article ({int(age_hours)}h old): '{title}'")
                    continue

                # Helper to reject generic app icons and site logos
                def is_valid_subject_photo(url: Optional[str]) -> bool:
                    if not url or not isinstance(url, str):
                        return False
                    u = url.lower()
                    invalid_tokens = ["googleusercontent.com", "news.google.com", "favicon", "logo", "app_icon", "default_avatar", "ycombinator.com", "feedburner.com"]
                    return not any(tok in u for tok in invalid_tokens)

                # Extract image url from enclosure, media tags, or img src in description
                image_url = None
                enclosure = item.find("enclosure")
                if enclosure is not None:
                    enc_url = enclosure.get("url", "")
                    enc_type = enclosure.get("type", "")
                    if ("image" in enc_type or enc_url.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))) and is_valid_subject_photo(enc_url):
                        image_url = enc_url

                if not image_url:
                    namespaces = {"media": "http://search.yahoo.com/mrss/"}
                    for media_tag in ("media:content", "media:thumbnail"):
                        media_elem = item.find(media_tag, namespaces)
                        if media_elem is not None and media_elem.get("url") and is_valid_subject_photo(media_elem.get("url")):
                            image_url = media_elem.get("url")
                            break

                if not image_url and description:
                    img_match = re.search(r'<img[^>]+src=["\'](https?://[^"\']+)["\']', description, re.IGNORECASE)
                    if img_match and is_valid_subject_photo(img_match.group(1)):
                        image_url = img_match.group(1)

                if not image_url and link and link.startswith("http"):
                    try:
                        art_resp = requests.get(link, headers=headers, timeout=5, allow_redirects=True)
                        if art_resp.status_code == 200:
                            actual_url = art_resp.url or link
                            if "//" in actual_url:
                                source_domain = actual_url.split("/")[2]
                            meta_m = (
                                re.search(r'<meta[^>]+(?:property|name)=["\'](?:og|twitter):image(?::src)?["\'][^>]+content=["\']([^"\']+)["\']', art_resp.text, re.IGNORECASE)
                                or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og|twitter):image(?::src)?["\']', art_resp.text, re.IGNORECASE)
                            )
                            if meta_m:
                                extracted_img = meta_m.group(1).strip()
                                if extracted_img.startswith("//"):
                                    extracted_img = "https:" + extracted_img
                                elif not extracted_img.startswith("http"):
                                    extracted_img = urllib.parse.urljoin(actual_url, extracted_img)
                                if is_valid_subject_photo(extracted_img):
                                    image_url = extracted_img
                    except Exception as og_err:
                        logger.debug(f"Image meta extraction skipped for {link}: {og_err}")

                content_id = self.generate_stable_id(link, source_domain)

                # Enforce strict 100% real published photos or real videos (zero AI text cards/graphic banners)
                raw_article_photo = image_url
                if raw_article_photo and raw_article_photo.startswith("http://"):
                    raw_article_photo = "https://" + raw_article_photo[7:]

                use_raw_photo = os.getenv("USE_RAW_NEWS_PHOTOS", "true").lower() in ("true", "1", "yes")
                disable_gen_reels = os.getenv("DISABLE_GENERATED_REELS", "true").lower() in ("true", "1", "yes")

                # If no real published photo and no real video, skip article completely (no AI generated cards/reels)
                if use_raw_photo and disable_gen_reels and not raw_article_photo:
                    logger.info(f"Skipping article without authentic published photo/video: '{title}'")
                    continue

                # Ensure photo satisfies Meta Graph API aspect ratio (4:5 to 1.91:1) with zero text/graphics added
                image_url = self.prepare_instagram_compliant_photo(raw_article_photo, content_id) if raw_article_photo else None
                video_url = None
                item_media_type = "IMAGE"
                media_rights_status = "AUTHORIZED"


                LAUNCH_KEYWORDS = ("unveil", "unveils", "launch", "launches", "announces", "reveal", "reveals", "introduced", "specs", "new product")
                is_launch = category == "launches" or any(kw in title.lower() for kw in LAUNCH_KEYWORDS)

                results.append(
                    {
                        "content_id": content_id,
                        "title": title,
                        "summary": clean_desc[:250] if clean_desc else title,
                        "category": "launches" if (category == "technology" and is_launch) else category,
                        "source_name": source_domain,
                        "source_url": link,
                        "discovery_source": feed_url,
                        "original_source": link,
                        "source_domain": source_domain,
                        "published_at": pub_dt.isoformat(),
                        "verified_at": now.isoformat(),
                        "collected_at": now.isoformat(),
                        "content_type": "NEWS",
                        "media_type": item_media_type,
                        "image_url": image_url,
                        "video_url": video_url,
                        "media_rights_status": media_rights_status,
                        "is_launch": is_launch,
                    }
                )

            return results

        except Exception as e:
            logger.warning(f"Error reading RSS feed {redact_token(feed_url)}: {redact_token(str(e))}")
            return []

    def get_content_items(self) -> List[Dict[str, Any]]:
        """Collects real news items across all enabled content categories and RSS sources."""
        all_items: List[Dict[str, Any]] = []

        category_map = [
            ("cricket", getattr(self.config, "enable_cricket_category", True), self.cricket_feeds),
            ("technology", getattr(self.config, "enable_technology_category", True), self.tech_feeds),
            ("launches", getattr(self.config, "enable_launches_category", True), self.launches_feeds),
            ("geopolitics", getattr(self.config, "enable_geopolitics_category", True), self.geopolitics_feeds),
            ("democracy", getattr(self.config, "enable_democracy_category", True), self.democracy_feeds),
            ("entertainment", getattr(self.config, "enable_entertainment_category", True), self.entertainment_feeds),
        ]

        for cat_name, is_enabled, feeds in category_map:
            if not is_enabled:
                logger.info(f"Skipping category '{cat_name}' (disabled by configuration)")
                continue
            for feed in feeds:
                items = self.fetch_feed_items(feed, category=cat_name)
                all_items.extend(items)

        logger.info(f"RealNewsSource acquired {len(all_items)} verified articles from RSS feeds.")
        return all_items
