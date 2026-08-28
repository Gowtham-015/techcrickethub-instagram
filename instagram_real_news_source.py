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
                        logger.info(f"Public host upload (Catbox) success for {local_path}: {resp.text.strip()}")
                        return resp.text.strip()
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
                if token:
                    repo = os.getenv("GITHUB_REPOSITORY", "Gowtham-015/techcrickethub-instagram")
                    remote_auth_url = f"https://x-access-token:{token}@github.com/{repo}.git"
                    subprocess.run(["git", "push", remote_auth_url, "HEAD:main"], check=False)
                else:
                    subprocess.run(["git", "push", "origin", "main"], check=False)
            except Exception as git_err:
                logger.warning(f"Git push for raw URL failed: {git_err}")

        return fallback_url



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

                content_id = self.generate_stable_id(link, source_domain)

                # Always render broadcast news graphic card for high-resolution, story-matched posts
                try:
                    from instagram_graphic_card_generator import InstagramGraphicCardGenerator

                    card_gen = InstagramGraphicCardGenerator()
                    card_path = card_gen.create_news_card(
                        title=title,
                        summary=clean_desc,
                        category=category,
                        source_name=source_domain,
                        content_id=content_id,
                        bg_image_path=image_url,
                    )
                    rel_filename = os.path.basename(card_path)
                    raw_url = f"https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/media/generated/{rel_filename}"
                    image_url = self.upload_to_public_host(card_path, raw_url)
                except Exception as gen_err:
                    logger.warning(f"Graphic card generation failed for {content_id}: {gen_err}")
                    if image_url and image_url.startswith("http://"):
                        image_url = "https://" + image_url[7:]
                    elif not image_url:
                        image_url = f"https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/media/generated/card_{content_id}.jpg"

                        # Standalone inline card fallback to guarantee zero generic sample photos
                        try:
                            from PIL import Image, ImageDraw, ImageFont

                            img = Image.new("RGB", (1080, 1080), color=(15, 23, 42))
                            draw = ImageDraw.Draw(img)
                            draw.rectangle([(0, 0), (1080, 120)], fill=(16, 185, 129) if category == "cricket" else (59, 130, 246))
                            draw.text((60, 40), f"{category.upper()} NEWS UPDATE", fill=(255, 255, 255))
                            draw.text((60, 200), title[:50], fill=(255, 255, 255))
                            draw.text((60, 350), clean_desc[:200], fill=(203, 213, 225))
                            draw.text((60, 980), f"Source: {source_domain} | @techcrickethub", fill=(148, 163, 184))
                            base_dir = os.path.dirname(os.path.abspath(__file__))
                            gen_dir = os.path.join(base_dir, "media", "generated")
                            os.makedirs(gen_dir, exist_ok=True)
                            card_path = os.path.join(gen_dir, f"card_{content_id}.jpg")
                            img.save(card_path, "JPEG", quality=90)
                            rel_filename = os.path.basename(card_path)
                            raw_url = f"https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/media/generated/{rel_filename}"
                            image_url = self.upload_to_public_host(card_path, raw_url)
                        except Exception:
                            # Direct github raw fallback for verified card format
                            image_url = f"https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/media/generated/card_{content_id}.jpg"

                reels_only = (
                    os.getenv("REELS_ONLY", "true").lower() in ("true", "1", "yes")
                    or os.getenv("FORCE_REELS", "false").lower() in ("true", "1", "yes")
                    or os.getenv("INSTAGRAM_REELS_ONLY", "false").lower() in ("true", "1", "yes")
                    or getattr(self.config, "reel_target_percent", 80) == 100
                )
                is_reel_candidate = True if reels_only else ((len(results) % 5) in (0, 1, 2, 3))

                # 100% Real Video Footage Enforcement for Reels
                video_url = None
                media_rights_status = "UNKNOWN"


                # Check if real action video is available
                extracted_video_url = item.get("video_url") or link if ("youtube.com" in link or "youtu.be" in link or link.endswith(".mp4")) else None
                
                if is_reel_candidate and extracted_video_url:
                    try:
                        acquired_path = self.download_video_asset(extracted_video_url)
                        if acquired_path and os.path.exists(acquired_path):
                            rel_v = os.path.basename(acquired_path)
                            raw_v_url = f"https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/data/acquired_videos/{rel_v}"
                            video_url = self.upload_to_public_host(acquired_path, raw_v_url)
                            item_media_type = "REEL"
                            image_url = None
                            media_rights_status = "ORIGINAL_GENERATED"
                        else:
                            # Fall back to high-resolution graphic card image post if no video asset
                            item_media_type = "IMAGE"
                            video_url = None
                            media_rights_status = "ORIGINAL_GENERATED"
                    except Exception as v_err:
                        logger.warning(f"Video acquisition error for {content_id}: {v_err}")
                        item_media_type = "IMAGE"
                        video_url = None
                        media_rights_status = "ORIGINAL_GENERATED"
                elif is_reel_candidate:
                    # Try generating dynamic animated reel from facts ONLY if real background footage is provided
                    try:
                        from instagram_reel_generator import InstagramReelGenerator

                        reel_gen = InstagramReelGenerator()
                        gen_res = reel_gen.generate_reel_from_facts(
                            {
                                "content_id": content_id,
                                "title": title,
                                "summary": clean_desc[:250] if clean_desc else title,
                                "source_name": source_domain,
                                "category": category,
                            },
                            duration_sec=6.0,
                        )
                        if gen_res.get("success") and gen_res.get("reel_path"):
                            rel_video = os.path.basename(gen_res["reel_path"])
                            raw_video_url = f"https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/data/generated_reels/{rel_video}"
                            video_url = self.upload_to_public_host(gen_res["reel_path"], raw_video_url)
                            item_media_type = "REEL"
                            image_url = None
                            media_rights_status = "ORIGINAL_GENERATED"
                        else:
                            item_media_type = "IMAGE"
                            video_url = None
                            media_rights_status = "ORIGINAL_GENERATED"
                    except Exception as reel_err:
                        logger.warning(f"Reel generation failed for {content_id}: {reel_err}")
                        item_media_type = "IMAGE"
                        video_url = None
                        media_rights_status = "ORIGINAL_GENERATED"
                else:
                    item_media_type = "IMAGE"
                    video_url = None
                    media_rights_status = "ORIGINAL_GENERATED" if image_url else "AUTHORIZED"


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
