import logging
import os
import re
import time
from typing import Any, Dict, Optional
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("InstagramGraphicCardGenerator")


class InstagramGraphicCardGenerator:
    """Generates premium 1080x1080 branded graphic news cards for Instagram posts."""

    def __init__(self, output_dir: Optional[str] = None):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.output_dir = output_dir or os.path.join(base_dir, "media", "generated")
        os.makedirs(self.output_dir, exist_ok=True)

    @staticmethod
    def wrap_text(text: str, max_chars_per_line: int = 24) -> list:
        """Wraps text into a list of lines fitting max_chars_per_line."""
        words = text.split()
        lines = []
        current_line = ""
        for word in words:
            if len(current_line + " " + word) <= max_chars_per_line:
                current_line = (current_line + " " + word).strip()
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        return lines

    def get_font(self, size: int):
        """Loads a TTF font or scaled default font."""
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

    def create_news_card(
        self,
        title: str,
        summary: str,
        category: str = "cricket",
        source_name: str = "ESPNCricinfo",
        content_id: str = "",
        bg_image_path: Optional[str] = None,
    ) -> str:
        """Renders a 1080x1080 square news graphic card and saves to output_dir."""
        width, height = 1080, 1080
        is_cricket = category.lower() == "cricket"

        # Color palette & branding
        header_bg = (16, 185, 129) if is_cricket else (14, 165, 233)  # Emerald green / Sky blue
        header_text = "CRICKET BREAKING NEWS" if is_cricket else "TECHNOLOGY NEWS UPDATE"
        accent_color = (52, 211, 153) if is_cricket else (56, 189, 248)

        # Base Image Creation
        temp_bg_path = None
        if bg_image_path and str(bg_image_path).startswith("http"):
            try:
                import requests
                r = requests.get(bg_image_path, timeout=10)
                if r.status_code == 200:
                    temp_bg_path = os.path.join(self.output_dir, f"temp_card_bg_{int(time.time())}.jpg")
                    with open(temp_bg_path, "wb") as f:
                        f.write(r.content)
                    bg_image_path = temp_bg_path
            except Exception as e:
                logger.warning(f"Error downloading bg image for graphic card: {e}")
                bg_image_path = None

        if bg_image_path and os.path.exists(bg_image_path):
            try:
                base_img = Image.open(bg_image_path).convert("RGB")
                # Crop to 1080x1080 square
                img_ratio = base_img.width / base_img.height
                if img_ratio > 1.0:
                    new_h = height
                    new_w = int(new_h * img_ratio)
                else:
                    new_w = width
                    new_h = int(new_w / img_ratio)
                resized = base_img.resize((max(width, new_w), max(height, new_h)), Image.Resampling.LANCZOS)
                left = (resized.width - width) // 2
                top = (resized.height - height) // 2
                img = resized.crop((left, top, left + width, top + height)).convert("RGB")
            except Exception as e:
                logger.warning(f"Error processing background image: {e}")
                img = Image.new("RGB", (width, height), color=(15, 23, 42))
        else:
            img = Image.new("RGB", (width, height), color=(15, 23, 42))

        # Add frosted glass overlay card for high legibility
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)

        # Top Header Bar
        overlay_draw.rectangle([(0, 0), (width, 130)], fill=(*header_bg, 255))

        # Main Text Container Overlay Box (y=160 to 950)
        overlay_draw.rectangle([(40, 160), (width - 40, 950)], fill=(15, 23, 42, 220), outline=(51, 65, 85, 255), width=3)
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(img)

        # Fonts
        font_header = self.get_font(38)
        font_title = self.get_font(42)
        font_summary = self.get_font(28)
        font_footer = self.get_font(26)

        # Header Text
        draw.text((60, 42), f"★  {header_text}", fill=(255, 255, 255), font=font_header)

        # Title Card Box (Inside container box)
        draw.rectangle([(70, 190), (width - 70, 600)], fill=(30, 41, 59), outline=accent_color, width=3)

        # Draw wrapped title lines
        title_lines = self.wrap_text(title, max_chars_per_line=24)
        y_pos = 220
        for line in title_lines[:5]:
            draw.text((100, y_pos), line, fill=(255, 255, 255), font=font_title)
            y_pos += 72

        # Summary / Facts Box
        if summary and summary.strip() != title.strip():
            draw.rectangle([(70, 630), (width - 70, 920)], fill=(24, 32, 47), outline=(71, 85, 105), width=2)
            draw.text((100, 650), "★ MATCH HIGHLIGHTS & INSIGHTS", fill=accent_color, font=font_footer)
            summary_clean = re.sub(r"\s+", " ", summary).strip()
            summary_lines = self.wrap_text(summary_clean, max_chars_per_line=40)
            y_sum = 695
            for s_line in summary_lines[:4]:
                draw.text((100, y_sum), s_line, fill=(226, 232, 240), font=font_summary)
                y_sum += 46

        # Footer Bar with Source & Brand
        draw.rectangle([(0, 970), (width, height)], fill=(15, 23, 42))
        draw.line([(0, 970), (width, 970)], fill=(51, 65, 85), width=3)
        draw.text((60, 1005), f"Source: {source_name}", fill=(148, 163, 184), font=font_footer)
        draw.text((720, 1005), "@techcrickethub", fill=accent_color, font=font_footer)

        # Cleanup temp file
        if temp_bg_path and os.path.exists(temp_bg_path):
            try:
                os.remove(temp_bg_path)
            except Exception:
                pass

        # Save Image
        cid = content_id or f"real_{int(time.time())}"
        filename = f"card_{cid}.jpg"
        file_path = os.path.join(self.output_dir, filename)
        img.save(file_path, quality=95)
        logger.info(f"Generated broadcast news graphic card: {file_path}")

        return file_path

