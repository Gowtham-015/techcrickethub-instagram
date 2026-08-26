import logging
import os
import time
from typing import Any, Dict, Optional
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from security import redact_token

logger = logging.getLogger("InstagramReelGenerator")


class InstagramReelGenerator:
    """Generates original 5-15s data-driven animation Reels from verified match data and facts.

    Uses Pillow frame generation and safe video creation without fake AI match footage.
    """

    def __init__(self, output_dir: Optional[str] = None):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.output_dir = output_dir or os.path.join(base_dir, "data", "generated_reels")
        os.makedirs(self.output_dir, exist_ok=True)

    def get_font(self, size: int) -> Any:
        """Loads a clean TrueType font at requested size, falling back to default."""
        font_paths = [
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/calibrib.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
        for path in font_paths:
            if os.path.exists(path):
                try:
                    return ImageFont.truetype(path, size)
                except Exception:
                    pass
        try:
            return ImageFont.load_default(size=size)
        except Exception:
            return ImageFont.load_default()

    def wrap_text(self, text: str, max_chars_per_line: int = 32) -> list:
        """Wraps text into clean lines for vertical 9:16 layout."""
        words = text.split()
        lines = []
        current_line = []
        current_length = 0
        for word in words:
            if current_length + len(word) + 1 <= max_chars_per_line:
                current_line.append(word)
                current_length += len(word) + 1
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                current_line = [word]
                current_length = len(word)
        if current_line:
            lines.append(" ".join(current_line))
        return lines

    def render_frame(
        self,
        title: str,
        subtitle: str,
        fact_text: str,
        source: str,
        bg_image_path: Optional[str] = None,
        width: int = 1080,
        height: int = 1920,
        frame_idx: int = 0,
    ) -> Any:
        """Renders an original 1080x1920 vertical graphic frame with match photo background and dark gradient overlay."""
        # 1. Base Image background
        if bg_image_path and os.path.exists(bg_image_path):
            try:
                base_img = Image.open(bg_image_path).convert("RGB")
                # Crop/resize to 1080x1920 9:16 aspect ratio
                img_ratio = base_img.width / base_img.height
                target_ratio = width / height
                if img_ratio > target_ratio:
                    new_width = int(height * img_ratio)
                    resized = base_img.resize((new_width, height), Image.Resampling.LANCZOS)
                    left = (new_width - width) // 2
                    img = resized.crop((left, 0, left + width, height))
                else:
                    new_height = int(width / img_ratio)
                    resized = base_img.resize((width, new_height), Image.Resampling.LANCZOS)
                    top = (new_height - height) // 2
                    img = resized.crop((0, top, width, top + height))
            except Exception as e:
                logger.warning(f"Error loading bg_image_path: {e}")
                img = Image.new("RGB", (width, height), color=(15, 23, 42))
        else:
            img = Image.new("RGB", (width, height), color=(15, 23, 42))

        # 2. Add dark gradient overlay to bottom half for high contrast readability
        draw = ImageDraw.Draw(img, "RGBA")
        # Gradient overlay from y=700 to 1920
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        # Top banner overlay (y=0 to 220)
        overlay_draw.rectangle([(0, 0), (width, 220)], fill=(15, 23, 42, 220))
        # Bottom card overlay (y=800 to 1920)
        overlay_draw.rectangle([(0, 800), (width, height)], fill=(15, 23, 42, 235))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(img)

        # 3. Fonts
        font_header = self.get_font(42)
        font_title = self.get_font(48)
        font_fact = self.get_font(34)
        font_footer = self.get_font(28)

        # 4. Top Category Header Bar
        draw.rectangle([(0, 0), (width, 110)], fill=(16, 185, 129))
        draw.text((60, 32), "★  LIVE CRICKET TEST MATCH UPDATE", fill=(255, 255, 255), font=font_header)

        # 5. Title Card Box
        draw.rectangle([(50, 840), (1030, 1100)], fill=(30, 41, 59), outline=(16, 185, 129), width=4)
        title_lines = self.wrap_text(title, max_chars_per_line=30)
        y_title = 860
        for t_line in title_lines[:3]:
            draw.text((80, y_title), t_line, fill=(255, 255, 255), font=font_title)
            y_title += 56

        # 6. Fact Details Box
        draw.rectangle([(50, 1140), (1030, 1720)], fill=(24, 32, 47), outline=(71, 85, 105), width=3)
        fact_lines = self.wrap_text(fact_text, max_chars_per_line=36)
        y_fact = 1170
        for f_line in fact_lines[:8]:
            draw.text((80, y_fact), f_line, fill=(226, 232, 240), font=font_fact)
            y_fact += 48

        # 7. Mandatory Source Attribution Footer Bar
        draw.rectangle([(0, height - 140), (width, height)], fill=(15, 23, 42))
        draw.line([(0, height - 140), (width, height - 140)], fill=(51, 65, 85), width=3)
        draw.text((60, height - 95), f"Source: {source}", fill=(148, 163, 184), font=font_footer)
        draw.text((700, height - 95), "@techcrickethub", fill=(52, 211, 153), font=font_footer)

        return img

    def generate_reel_from_facts(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Generates an original Reel video file from verified content item facts."""
        if not PIL_AVAILABLE:
            return {
                "success": False,
                "action": "SKIP_REEL",
                "reason": "Graphic rendering library (Pillow) not installed.",
                "reel_path": None,
            }
        content_id = item.get("content_id", f"gen-{int(time.time())}")
        title = item.get("title", "Cricket Match Update")
        summary = item.get("summary", "Verified match statistics and update.")
        source = item.get("source_name") or item.get("source") or "Verified Data Provider"
        bg_image_path = item.get("bg_image_path") or item.get("image_path") or item.get("image_url")

        # Download remote bg_image_url if passed
        temp_bg_path = None
        if bg_image_path and str(bg_image_path).startswith("http"):
            try:
                import requests
                r = requests.get(bg_image_path, timeout=10)
                if r.status_code == 200:
                    temp_bg_path = os.path.join(self.output_dir, f"temp_bg_{content_id}.jpg")
                    with open(temp_bg_path, "wb") as f:
                        f.write(r.content)
                    bg_image_path = temp_bg_path
            except Exception as e:
                logger.warning(f"Error downloading bg image for reel: {e}")
                bg_image_path = None

        filename = f"reel_{content_id}.mp4"
        file_path = os.path.join(self.output_dir, filename)

        try:
            # Generate frames
            frames = []
            for idx in range(3):
                frame_img = self.render_frame(
                    title=title,
                    subtitle="LIVE CRICKET TEST MATCH UPDATE",
                    fact_text=summary,
                    source=source,
                    bg_image_path=bg_image_path,
                    frame_idx=idx,
                )
                frame_path = os.path.join(self.output_dir, f"frame_{idx}.png")
                frame_img.save(frame_path)
                frames.append(frame_path)

            if temp_bg_path and os.path.exists(temp_bg_path):
                try:
                    os.remove(temp_bg_path)
                except Exception:
                    pass

            # Use imageio_ffmpeg binary via subprocess to generate Meta-compliant faststart H.264 + AAC MP4 Reel
            try:
                import imageio_ffmpeg
                import subprocess

                ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                frame_0 = frames[0]

                cmd = [
                    ffmpeg_exe,
                    "-y",
                    "-loop",
                    "1",
                    "-i",
                    frame_0,
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=220:sample_rate=48000",
                    "-c:v",
                    "libx264",
                    "-t",
                    "10",
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                    "-ar",
                    "48000",
                    "-r",
                    "30",
                    file_path,
                ]

                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
                if res.returncode != 0:
                    logger.warning(f"ffmpeg execution failed: {res.stderr.decode('utf-8', errors='ignore')}")
                    raise RuntimeError("FFmpeg encoding failed.")

            except Exception as vid_err:
                logger.warning(f"FFmpeg encoding error: {vid_err}, trying cv2 fallback")
                try:
                    import cv2
                    import numpy as np

                    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                    writer = cv2.VideoWriter(file_path, fourcc, 24.0, (1080, 1920))

                    for frame_path in frames:
                        img_np = cv2.imread(frame_path)
                        for _ in range(48):
                            writer.write(img_np)
                    writer.release()
                except Exception as cv_err:
                    logger.info(f"Video assembly failed: {cv_err}")
                    return {
                        "success": False,
                        "action": "SKIP_REEL",
                        "reason": f"Video encoding error: {cv_err}",
                        "reel_path": None,
                    }

            # Cleanup frame PNGs
            for f in frames:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except Exception:
                        pass

            logger.info(f"Generated original data Reel: {file_path}")
            return {
                "success": True,
                "action": "REEL_GENERATED",
                "reel_path": file_path,
                "duration_seconds": 6.0,
                "source_attributed": source,
                "media_rights_status": "ORIGINAL_GENERATED",
            }

        except Exception as e:
            logger.warning(f"Failed to generate original Reel: {redact_token(str(e))}")
            return {
                "success": False,
                "action": "SKIP_REEL",
                "reason": f"Reel generation error: {redact_token(str(e))}",
                "reel_path": None,
            }
