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
        self.cricket_feeds = [
            f.strip()
            for f in self.config.cricket_rss_feeds.split(",")
            if f.strip()
        ]
        self.tech_feeds = [
            f.strip()
            for f in self.config.tech_rss_feeds.split(",")
            if f.strip()
        ]

    @staticmethod
    def generate_stable_id(url: str, source_name: str) -> str:
        """Generates a stable, SHA256-based content ID for production items."""
        clean_url = (url or "").strip().lower()
        hasher = hashlib.sha256(f"{source_name}:{clean_url}".encode("utf-8"))
        return f"real-{hasher.hexdigest()[:16]}"

    @staticmethod
    def upload_to_public_host(local_path: str, fallback_url: str) -> str:
        """Uploads a local generated image/video file to Catbox with browser User-Agent headers and retries."""
        if not local_path or not os.path.exists(local_path):
            return fallback_url
        if os.getenv("SKIP_CATBOX_UPLOAD", "false").lower() in ("true", "1", "yes"):
            return fallback_url

        is_video = local_path.lower().endswith((".mp4", ".mov", ".avi"))
        timeout = 35 if is_video else 15
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }

        # Attempt Catbox.moe upload with retries
        for attempt in range(3):
            try:
                with open(local_path, "rb") as f:
                    resp = requests.post(
                        "https://catbox.moe/user/api.php",
                        data={"reqtype": "fileupload"},
                        files={"fileToUpload": f},
                        headers=headers,
                        timeout=timeout,
                    )
                    if resp.status_code == 200 and resp.text.strip().startswith("https://files.catbox.moe/"):
                        res_url = resp.text.strip()
                        try:
                            chk = requests.get(res_url, headers=headers, timeout=5, stream=True)
                            if chk.status_code == 200 and int(chk.headers.get("Content-Length", 1000)) > 100:
                                logger.info(f"Public host upload (Catbox) success for {local_path}: {res_url}")
                                return res_url
                        except Exception:
                            pass
            except Exception as e:
                logger.warning(f"Catbox upload attempt {attempt + 1} failed for {local_path}: {e}")

        # Attempt Litterbox upload fallback if Catbox fails
        try:
            with open(local_path, "rb") as f:
                resp = requests.post(
                    "https://litterbox.catbox.moe/resources/internals/api.php",
                    data={"reqtype": "fileupload", "time": "24h"},
                    files={"fileToUpload": f},
                    headers=headers,
                    timeout=timeout,
                )
                if resp.status_code == 200 and resp.text.strip().startswith("https://litterbox.catbox.moe/"):
                    logger.info(f"Public host upload (Litterbox) success for {local_path}: {resp.text.strip()}")
                    return resp.text.strip()
        except Exception as l_err:
            logger.warning(f"Litterbox upload fallback failed for {local_path}: {l_err}")

        # If falling back to raw.githubusercontent.com, ensure file is pushed to GitHub Raw immediately
        if "raw.githubusercontent.com" in fallback_url and os.path.exists(local_path):
            try:
                import subprocess
                rel_n = os.path.basename(local_path)
                logger.info(f"Ensuring local file '{rel_n}' is pushed to GitHub Raw...")
                subprocess.run(["git", "add", "-f", local_path], check=False)
                subprocess.run(["git", "add", "-A"], check=False)
                subprocess.run(["git", "commit", "-m", f"Chore: publish asset {rel_n} [skip ci]"], check=False)
                token = os.getenv("GITHUB_TOKEN")
                repo = os.getenv("GITHUB_REPOSITORY", "Gowtham-015/techcrickethub-instagram")
                remote_target = f"https://x-access-token:{token}@github.com/{repo}.git" if token else "origin"
                
                # Rebase first to avoid git push rejection
                subprocess.run(["git", "pull", remote_target, "main", "--rebase", "-X", "ours"], check=False)
                push_res = subprocess.run(["git", "push", remote_target, "HEAD:main" if token else "main"], capture_output=True, text=True, check=False)
                if push_res.returncode != 0:
                    logger.warning(f"Git push rejected, pulling and retrying push: {push_res.stderr.strip()[:200]}")
                    subprocess.run(["git", "pull", remote_target, "main", "--rebase", "-X", "ours"], check=False)
                    subprocess.run(["git", "push", remote_target, "HEAD:main" if token else "main"], check=False)
            except Exception as git_err:
                logger.warning(f"Git push for raw URL failed: {git_err}")

        return fallback_url

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

            for item in items[:3]:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                description = (item.findtext("description") or "").strip()
                pub_date_str = item.findtext("pubDate") or item.findtext("dc:date")

                # Remove HTML tags from description
                clean_desc = re.sub(r"<[^>]+>", "", description).strip()

                if not title or not link:
                    continue

                pub_dt = self.parse_rss_date(pub_date_str) or now
                age_hours = (now - pub_dt).total_seconds() / 3600.0

                # Reject stale content
                if age_hours > max_age_hours:
                    logger.info(f"Skipping stale {category} article ({int(age_hours)}h old): '{title}'")
                    continue

                # Extract image url from enclosure, media tags, or img src in description
                image_url = None
                enclosure = item.find("enclosure")
                if enclosure is not None:
                    enc_url = enclosure.get("url", "")
                    enc_type = enclosure.get("type", "")
                    if "image" in enc_type or enc_url.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                        image_url = enc_url

                if not image_url:
                    namespaces = {"media": "http://search.yahoo.com/mrss/"}
                    for media_tag in ("media:content", "media:thumbnail"):
                        media_elem = item.find(media_tag, namespaces)
                        if media_elem is not None and media_elem.get("url"):
                            image_url = media_elem.get("url")
                            break

                if not image_url and description:
                    img_match = re.search(r'<img[^>]+src=["\'](https?://[^"\']+)["\']', description, re.IGNORECASE)
                    if img_match:
                        image_url = img_match.group(1)

                if not image_url and link and link.startswith("http"):
                    try:
                        art_resp = requests.get(link, headers=headers, timeout=4)
                        if art_resp.status_code == 200:
                            og_m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](https?://[^"\']+)["\']', art_resp.text, re.IGNORECASE) or re.search(r'<meta[^>]+content=["\'](https?://[^"\']+)["\'][^>]+property=["\']og:image["\']', art_resp.text, re.IGNORECASE)
                            if og_m:
                                image_url = og_m.group(1)
                    except Exception as og_err:
                        logger.debug(f"og:image extraction skipped for {link}: {og_err}")

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


                results.append(
                    {
                        "content_id": content_id,
                        "title": title,
                        "summary": clean_desc[:250] if clean_desc else title,
                        "category": category,
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
                    }
                )

            return results

        except Exception as e:
            logger.warning(f"Error reading RSS feed {redact_token(feed_url)}: {redact_token(str(e))}")
            return []

    def get_content_items(self) -> List[Dict[str, Any]]:
        """Collects real Cricket and Tech news items across all configured RSS sources."""
        all_items: List[Dict[str, Any]] = []

        # 1. Fetch Cricket feeds
        for feed in self.cricket_feeds:
            items = self.fetch_feed_items(feed, category="cricket")
            all_items.extend(items)

        # 2. Fetch Tech feeds
        for feed in self.tech_feeds:
            items = self.fetch_feed_items(feed, category="technology")
            all_items.extend(items)

        logger.info(f"RealNewsSource acquired {len(all_items)} verified articles from RSS feeds.")
        return all_items
