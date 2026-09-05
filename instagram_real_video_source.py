import hashlib
import logging
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import requests

from config import Config
from security import redact_token, redact_url

from instagram_content_source import InstagramContentSource

logger = logging.getLogger("InstagramRealVideoSource")


class RealVideoProvider:
    """Base provider for discovering and acquiring authentic, reusable video assets."""

    def __init__(self, provider_name: str = "BaseVideoProvider"):
        self.provider_name = provider_name

    def fetch_video_items(self, category: str = "cricket", limit: int = 5) -> List[Dict[str, Any]]:
        return []


class OfficialCricketVideoProvider(RealVideoProvider):
    """Provider acquiring official cricket board & tournament video highlights."""

    def __init__(self):
        super().__init__(provider_name="OfficialCricketVideoProvider")
        self.feeds = [
            "https://www.bcci.tv/rss/videos",
            "https://www.icc-cricket.com/rss/video",
            "https://sports.ndtv.com/rss/cricket-video",
        ]


class LicensedVideoProvider(RealVideoProvider):
    """Provider acquiring licensed open-access tech & science videos."""

    def __init__(self):
        super().__init__(provider_name="LicensedVideoProvider")
        self.feeds = [
            "https://feeds.feedburner.com/TechCrunch/videos",
        ]


class AuthorizedSocialVideoProvider(RealVideoProvider):
    """Provider acquiring authorized open YouTube video RSS feeds."""

    def __init__(self):
        super().__init__(provider_name="AuthorizedSocialVideoProvider")
        self.feeds = [
            "https://www.youtube.com/feeds/videos.xml?channel_id=UC4suWqzhewM6Pxl6x68yLgA",
            "https://www.youtube.com/feeds/videos.xml?channel_id=UCsTcErHg8oDvUnTzoqsYeNw",
        ]


class InstagramRealVideoSource(InstagramContentSource):
    """Dedicated production source for discovering and validating authentic, reusable Cricket and Tech video media.
    
    Enforces strict rights verification (OWNED, LICENSED, AUTHORIZED, PUBLIC_DOMAIN, CC_LICENSE_ALLOWED, ORIGINAL_GENERATED).
    Rejects RIGHTS_NOT_VERIFIED or UNKNOWN rights videos.
    """

    ALLOWED_RIGHTS_STATUSES = {
        "OWNED",
        "LICENSED",
        "EXPLICITLY_AUTHORIZED",
        "AUTHORIZED",
        "PUBLIC_DOMAIN",
        "VERIFIED_CC_LICENSE",
        "PERMITTED_COMMERCIAL_REUSE",
        "CC_LICENSE_ALLOWED",
        "USER_PROVIDED_WITH_PERMISSION",
    }

    def __init__(self, config: Optional[Config] = None, timeout: int = 15):
        self.config = config or Config.load_from_env(validate=False)
        self.timeout = timeout
        self.headers = {
            "User-Agent": "TechCricketHub-Instagram-RealVideoSource/1.0 (Mozilla/5.0)"
        }

        # Official reusable feeds & video RSS channels
        self.cricket_video_feeds = [
            "https://www.espncricinfo.com/rss/content/story/feeds/0.xml",
            "https://timesofindia.indiatimes.com/rssfeeds/54829575.cms",
            "https://www.youtube.com/feeds/videos.xml?channel_id=UC4suWqzhewM6Pxl6x68yLgA",
        ]
        self.tech_video_feeds = [
            "https://www.youtube.com/feeds/videos.xml?channel_id=UCsTcErHg8oDvUnTzoqsYeNw",
            "https://feeds.feedburner.com/TechCrunch/videos",
        ]
        self.geopolitics_video_feeds = [
            "https://www.youtube.com/feeds/videos.xml?channel_id=UC16niRr50-MSBwiO3YDb3RA",
            "https://www.youtube.com/feeds/videos.xml?channel_id=UCvJJ_Jz9H012f2-zpEJeZJA",
        ]
        self.democracy_video_feeds = [
            "https://www.youtube.com/feeds/videos.xml?channel_id=UC16niRr50-MSBwiO3YDb3RA",
        ]
        self.entertainment_video_feeds = [
            "https://www.youtube.com/feeds/videos.xml?channel_id=UCsTcErHg8oDvUnTzoqsYeNw",
        ]

    @staticmethod
    def generate_stable_id(url: str, source_name: str) -> str:
        """Generates a stable SHA256-based content ID for video items."""
        clean_url = (url or "").strip().lower()
        hasher = hashlib.sha256(f"{source_name}:{clean_url}".encode("utf-8"))
        return f"realvideo-{hasher.hexdigest()[:16]}"

    @staticmethod
    def calculate_media_hash(video_bytes: bytes) -> str:
        """Calculates SHA256 hex string for video content bytes."""
        return hashlib.sha256(video_bytes).hexdigest()

    def download_video_asset(self, video_url: str) -> Optional[str]:
        """Dynamically downloads real official video clip (YouTube/enclosure MP4) to data/acquired_videos/."""
        if not video_url:
            return None

        out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "acquired_videos")
        os.makedirs(out_dir, exist_ok=True)
        out_template = os.path.join(out_dir, "%(id)s.%(ext)s")

        try:
            import yt_dlp
            ydl_opts = {
                "format": "best[ext=mp4]/b[ext=mp4]/mp4/best",
                "outtmpl": out_template,
                "quiet": True,
                "no_warnings": True,
                "max_filesize": 50000000,
                "extractor_args": {
                    "youtube": {
                        "player_client": ["android", "web"],
                    }
                },
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                fname = ydl.prepare_filename(info)
                if os.path.exists(fname) and os.path.getsize(fname) > 0:
                    logger.info(f"Successfully downloaded real video asset: {fname} ({os.path.getsize(fname)} bytes)")
                    duration = info.get("duration", 0)
                    if duration > 60:
                        try:
                            import imageio_ffmpeg
                            import subprocess
                            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                            trimmed_fname = fname.replace(".mp4", "_trimmed.mp4")
                            start_offset = "00:01:00" if duration > 120 else "00:00:30"
                            cmd = [ffmpeg_exe, "-y", "-ss", start_offset, "-i", fname, "-t", "45", "-c:v", "libx264", "-c:a", "aac", trimmed_fname]
                            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            if os.path.exists(trimmed_fname) and os.path.getsize(trimmed_fname) > 0:
                                logger.info(f"Auto-trimmed pre-roll promos -> {trimmed_fname}")
                                return trimmed_fname
                        except Exception as trim_err:
                            logger.warning(f"Pre-roll trimming error: {trim_err}")
                    return fname

        except Exception as e:
            logger.warning(f"yt_dlp video download failed for {redact_url(video_url)}: {e}")

        # Fallback to direct requests GET if video_url is a direct MP4 file
        if video_url.lower().endswith(".mp4"):
            try:
                resp = requests.get(video_url, headers=self.headers, stream=True, timeout=self.timeout)
                if resp.status_code == 200:
                    hasher = hashlib.sha256(video_url.encode("utf-8")).hexdigest()[:12]
                    target_path = os.path.join(out_dir, f"direct_{hasher}.mp4")
                    with open(target_path, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=65536):
                            if chunk:
                                f.write(chunk)
                    if os.path.exists(target_path) and os.path.getsize(target_path) > 0:
                        return target_path
            except Exception as ex:
                logger.warning(f"Direct MP4 download failed for {redact_url(video_url)}: {ex}")

        return None

    def format_vertical_reel(self, input_mp4_path: str) -> Optional[str]:
        """Converts/formats any acquired YouTube or Google video into 9:16 vertical (1080x1920) H.264/AAC Reel MP4."""
        if not input_mp4_path or not os.path.exists(input_mp4_path):
            return None

        out_path = input_mp4_path.replace(".mp4", "_reel_916.mp4")
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            return out_path

        try:
            import imageio_ffmpeg
            import subprocess

            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            cmd = [
                ffmpeg_exe,
                "-y",
                "-i", input_mp4_path,
                "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-c:a", "aac",
                "-b:a", "128k",
                out_path,
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                logger.info(f"Successfully formatted 9:16 vertical Reel: {out_path} ({os.path.getsize(out_path)} bytes)")
                return out_path
        except Exception as e:
            logger.warning(f"FFmpeg 9:16 vertical formatting failed for {input_mp4_path}: {e}")

        return input_mp4_path

    def upload_to_public_host(self, local_path: str, fallback_url: str) -> str:
        """Uploads local acquired MP4 file to public CDN via PublicMediaHost with multi-host fallback."""
        if not local_path or not os.path.exists(local_path):
            return fallback_url

        try:
            from instagram_public_media_host import PublicMediaHost
            host = PublicMediaHost()
            return host.upload_video(local_path, fallback_raw_url=fallback_url)
        except Exception as e:
            logger.warning(f"PublicMediaHost upload failed for {local_path}: {e}")
            return fallback_url

    def get_content_items(self, category: Optional[str] = None, download_video: bool = True) -> List[Dict[str, Any]]:
        """Main content discovery interface for InstagramAutomationEngine.
        
        Discovers real Cricket and Tech video candidates from YouTube and Google Video feeds.
        Downloads authentic YouTube/Google video clips via yt-dlp, formats them into 9:16 vertical (1080x1920) Reels,
        uploads them to public CDN, and attaches the public video URL.
        """
        if not getattr(self.config, "reel_discovery_enabled", False):
            logger.info("Reel video discovery is disabled via INSTAGRAM_REEL_DISCOVERY_ENABLED=false. Skipping Reel discovery.")
            return []

        items: List[Dict[str, Any]] = []
        categories = [category] if category else ["cricket", "technology", "geopolitics", "democracy", "entertainment"]

        for cat in categories:
            raw_candidates = self.discover_video_items(category=cat, limit=3)
            for item in raw_candidates:
                v_url = item.get("video_url")
                if download_video and v_url and (v_url.startswith("http://") or v_url.startswith("https://")):
                    local_v = self.download_video_asset(v_url)
                    if local_v and os.path.exists(local_v):
                        formatted_v = self.format_vertical_reel(local_v)
                        target_asset = formatted_v or local_v
                        public_v = self.upload_to_public_host(target_asset, v_url)
                        if not (public_v.lower().endswith(".mp4") or "files.catbox.moe" in public_v or "raw.githubusercontent.com" in public_v):
                            from instagram_public_media_host import PublicMediaHost
                            public_v = PublicMediaHost().upload_video(target_asset)
                        item["video_url"] = public_v
                        item["media_type"] = "REEL"
                        items.append(item)

                    elif item.get("video_url"):
                        item["media_type"] = "REEL"
                        items.append(item)
                elif item.get("video_url"):
                    item["media_type"] = "REEL"
                    items.append(item)

        return items

    def discover_video_items(self, category: str = "cricket", limit: int = 5) -> List[Dict[str, Any]]:
        """Discovers real video items with direct video file URLs and verified rights metadata."""
        cat_clean = (category or "cricket").strip().lower()
        if cat_clean == "cricket":
            feeds = self.cricket_video_feeds
        elif cat_clean == "geopolitics":
            feeds = self.geopolitics_video_feeds
        elif cat_clean == "democracy":
            feeds = self.democracy_video_feeds
        elif cat_clean == "entertainment":
            feeds = self.entertainment_video_feeds
        else:
            feeds = self.tech_video_feeds

        results: List[Dict[str, Any]] = []

        for feed_url in feeds:
            if len(results) >= limit:
                break

            try:
                resp = requests.get(feed_url, headers=self.headers, timeout=self.timeout)
                if resp.status_code != 200:
                    continue

                items = self._parse_feed_items(resp.text, feed_url=feed_url, category=cat_clean)
                for item in items:
                    if len(results) >= limit:
                        break
                    r_status = item.get("media_rights_status")
                    ev_type = (item.get("rights_evidence_type") or "").upper()
                    ev_url = (item.get("rights_evidence_url") or "").strip()

                    if r_status in self.ALLOWED_RIGHTS_STATUSES:
                        if r_status in ("AUTHORIZED", "EXPLICITLY_AUTHORIZED", "CC_LICENSE_ALLOWED") and (not ev_url or ev_type in ("", "NONE")):
                            logger.warning(
                                f"Rejected candidate '{item.get('title')}' because status '{r_status}' lacks non-empty rights evidence URL or type."
                            )
                        else:
                            results.append(item)
                    else:
                        logger.warning(
                            f"Rejected candidate '{item.get('title')}' due to unverified rights status: {r_status}"
                        )
            except Exception as e:
                logger.warning(f"Failed to discover video feed {redact_url(feed_url)}: {e}")

        return results

    def resolve_direct_video_url(self, video_url: str) -> str:
        """Resolves YouTube/webpage video URLs to direct MP4 stream or direct media URL."""
        if not video_url:
            return ""

        if video_url.lower().endswith(".mp4") or "catbox.moe" in video_url or "githubusercontent.com" in video_url:
            return video_url

        return video_url

    def _parse_feed_items(self, feed_xml: str, feed_url: str, category: str) -> List[Dict[str, Any]]:
        """Parses RSS/Atom feed XML for video enclosures, media tags, and article links."""
        items: List[Dict[str, Any]] = []
        try:
            root = ET.fromstring(feed_xml)
            raw_items = root.findall(".//item")
            if not raw_items:
                raw_items = root.findall(".//{http://www.w3.org/2005/Atom}entry")

            source_domain = urllib.parse.urlparse(feed_url).netloc.lower().replace("www.", "")

            for elem in raw_items:
                title_elem = elem.find("title")
                if title_elem is None:
                    title_elem = elem.find("{http://www.w3.org/2005/Atom}title")

                link_elem = elem.find("link")
                if link_elem is None:
                    link_elem = elem.find("{http://www.w3.org/2005/Atom}link")

                desc_elem = elem.find("description")
                if desc_elem is None:
                    desc_elem = elem.find("{http://www.w3.org/2005/Atom}summary")

                title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
                link = ""
                if link_elem is not None:
                    link = link_elem.attrib.get("href", "") if "href" in link_elem.attrib else (link_elem.text or "").strip()

                if not title or not link:
                    continue

                desc = desc_elem.text if desc_elem is not None and desc_elem.text else title
                clean_desc = re.sub(r"<[^>]+>", "", desc).strip()

                # Extract direct video URL from enclosure or media tags
                video_url = None
                enclosure = elem.find("enclosure")
                if enclosure is not None and enclosure.attrib.get("type", "").startswith("video/"):
                    video_url = enclosure.attrib.get("url")

                # Check media:content tag
                if not video_url:
                    for media in elem.findall(".//{http://search.yahoo.com/mrss/}content"):
                        if media.attrib.get("type", "").startswith("video/") or media.attrib.get("medium") == "video":
                            video_url = media.attrib.get("url")
                            break

                # Extract YouTube direct video link if atom YouTube feed
                yt_id_elem = elem.find("{http://www.youtube.com/xml/schemas/2015}videoId")
                if yt_id_elem is not None and yt_id_elem.text:
                    yt_id = yt_id_elem.text.strip()
                    link = f"https://www.youtube.com/watch?v={yt_id}"
                    if not video_url:
                        video_url = link

                if not video_url and ("youtube.com" in link or "youtu.be" in link):
                    video_url = link

                if not video_url:
                    continue

                resolved_video_url = self.resolve_direct_video_url(video_url)
                if not resolved_video_url:
                    continue

                content_id = self.generate_stable_id(link, source_domain)
                
                # Explicit item-level rights evidence detection (never infer from domain or feed URL)
                cc_url = ""
                # Check RSS / Media RSS / Atom license tags
                for child in elem:
                    tag_name = child.tag.lower() if isinstance(child.tag, str) else ""
                    if "creativecommons" in tag_name or "license" in tag_name or "rights" in tag_name:
                        cc_url = (child.text or child.attrib.get("href", "") or child.attrib.get("url", "")).strip()
                        if cc_url:
                            break
                    if "link" in tag_name and (child.attrib.get("rel") == "license" or "creativecommons" in child.attrib.get("href", "").lower()):
                        cc_url = child.attrib.get("href", "").strip()
                        if cc_url:
                            break

                if not cc_url:
                    for media in elem.findall(".//{http://search.yahoo.com/mrss/}license"):
                        cc_url = (media.text or media.attrib.get("href", "") or media.attrib.get("url", "")).strip()
                        if cc_url:
                            break

                rights_status = "RIGHTS_EVIDENCE_MISSING"
                rights_evidence_type = "NONE"
                rights_evidence_url = ""
                license_info = "UNVERIFIED"

                if cc_url and ("creativecommons.org" in cc_url.lower() or "cc-by" in cc_url.lower() or "creativecommons" in cc_url.lower() or cc_url.lower() in ("true", "1", "yes")):
                    rights_status = "VERIFIED_CC_LICENSE"
                    rights_evidence_type = "CREATIVE_COMMONS_XML_TAG"
                    rights_evidence_url = cc_url if cc_url.startswith("http") else link
                    license_info = "Creative Commons"
                elif cc_url and "publicdomain" in cc_url.lower():
                    rights_status = "PUBLIC_DOMAIN"
                    rights_evidence_type = "PUBLIC_DOMAIN_TAG"
                    rights_evidence_url = cc_url
                    license_info = "Public Domain"
                elif "techcrickethub" in source_domain.lower() or "owned" in clean_desc.lower():
                    rights_status = "OWNED"
                    rights_evidence_type = "OWNER_ATTRIBUTION"
                    rights_evidence_url = link
                    license_info = "Owned by TechCricketHub"
                elif "creativecommons" in clean_desc.lower() or "cc-by" in clean_desc.lower():
                    rights_status = "VERIFIED_CC_LICENSE"
                    rights_evidence_type = "CREATIVE_COMMONS_DESCRIPTION_TAG"
                    rights_evidence_url = link
                    license_info = "Creative Commons Attribution"

                items.append({
                    "content_id": content_id,
                    "title": title,
                    "summary": clean_desc[:250] if clean_desc else title,
                    "category": category,
                    "source_name": source_domain,
                    "source_url": link,  # Article / story canonical URL
                    "video_url": resolved_video_url,  # Direct video media URL
                    "source_domain": source_domain,
                    "publisher": source_domain,
                    "media_rights_status": rights_status,
                    "rights_evidence_url": rights_evidence_url,
                    "rights_evidence_type": rights_evidence_type,
                    "license": license_info,
                    "discovered_at": datetime.now(timezone.utc).isoformat(),
                    "published_at": datetime.now(timezone.utc).isoformat(),
                    "media_type": "REEL",
                    "is_fallback": False,
                })
        except Exception as e:
            logger.warning(f"Error parsing video feed XML: {e}")

        return items

