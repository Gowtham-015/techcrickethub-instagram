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

    def render_frame(
        self,
        title: str,
        subtitle: str,
        fact_text: str,
        source: str,
        width: int = 1080,
        height: int = 1920,
        frame_idx: int = 0,
    ) -> Any:
        """Renders an original 1080x1920 vertical graphic frame from verified facts."""
        img = Image.new("RGB", (width, height), color=(15, 23, 42))  # Dark slate theme
        draw = ImageDraw.Draw(img)

        # Header accent bar (Cricket green / tech blue)
        draw.rectangle([(0, 0), (width, 120)], fill=(16, 185, 129))

        try:
            title_font = ImageFont.load_default()
            subtitle_font = ImageFont.load_default()
        except Exception:
            title_font = None
            subtitle_font = None

        # Title
        draw.text((60, 200), title[:40], fill=(255, 255, 255), font=title_font)
        draw.line([(60, 260), (width - 60, 260)], fill=(51, 65, 85), width=4)

        # Subtitle / Tournament
        draw.text((60, 300), subtitle[:50], fill=(52, 211, 153), font=subtitle_font)

        # Fact details card
        draw.rectangle([(60, 420), (width - 60, 1400)], fill=(30, 41, 59), outline=(71, 85, 105), width=2)
        
        # Wrapped text for facts
        words = fact_text.split()
        line = ""
        y_offset = 480
        for word in words:
            if len(line + " " + word) < 30:
                line += " " + word
            else:
                draw.text((100, y_offset), line.strip(), fill=(241, 245, 249), font=title_font)
                y_offset += 60
                line = word
        if line:
            draw.text((100, y_offset), line.strip(), fill=(241, 245, 249), font=title_font)

        # Mandatory Source Attribution Footer
        draw.rectangle([(0, height - 160), (width, height)], fill=(15, 23, 42))
        draw.line([(0, height - 160), (width, height - 160)], fill=(51, 65, 85), width=2)
        draw.text((60, height - 120), f"Data Source: {source}", fill=(148, 163, 184), font=subtitle_font)
        draw.text((60, height - 70), "TechCricketHub Automation", fill=(100, 116, 139), font=subtitle_font)

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

        filename = f"reel_{content_id}.mp4"
        file_path = os.path.join(self.output_dir, filename)

        try:
            # Generate frames
            frames = []
            for idx in range(3):
                frame_img = self.render_frame(
                    title=title,
                    subtitle="CRICKET MATCH INTELLIGENCE",
                    fact_text=summary,
                    source=source,
                    frame_idx=idx,
                )
                frame_path = os.path.join(self.output_dir, f"frame_{idx}.png")
                frame_img.save(frame_path)
                frames.append(frame_path)

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
            }

        except Exception as e:
            logger.warning(f"Failed to generate original Reel: {redact_token(str(e))}")
            return {
                "success": False,
                "action": "SKIP_REEL",
                "reason": f"Reel generation error: {redact_token(str(e))}",
                "reel_path": None,
            }
