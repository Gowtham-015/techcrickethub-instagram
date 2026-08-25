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
    ) -> str:
        """Renders a 1080x1080 square news graphic card and saves to output_dir."""
        width, height = 1080, 1080

        # Color palette
        is_cricket = category.lower() == "cricket"
        bg_color = (15, 23, 42)  # Dark navy slate
        header_bg = (16, 185, 129) if is_cricket else (14, 165, 233)  # Emerald green / Sky blue
        header_text = "CRICKET BREAKING NEWS" if is_cricket else "TECHNOLOGY NEWS UPDATE"
        badge_symbol = "CRICKET" if is_cricket else "TECH UPDATE"

        img = Image.new("RGB", (width, height), color=bg_color)
        draw = ImageDraw.Draw(img)

        # Header bar
        draw.rectangle([(0, 0), (width, 130)], fill=header_bg)

        # Fonts
        font_header = self.get_font(38)
        font_title = self.get_font(42)
        font_summary = self.get_font(28)
        font_footer = self.get_font(26)

        # Header Text
        draw.text((60, 42), f"★  {header_text}", fill=(255, 255, 255), font=font_header)

        # Title Card Box
        draw.rectangle([(50, 170), (1030, 680)], fill=(30, 41, 59), outline=(51, 65, 85), width=4)

        # Draw wrapped title lines in bold white font
        title_lines = self.wrap_text(title, max_chars_per_line=24)
        y_pos = 210
        for line in title_lines[:6]:
            draw.text((90, y_pos), line, fill=(255, 255, 255), font=font_title)
            y_pos += 75

        # Summary / Facts Box
        if summary and summary.strip() != title.strip():
            draw.rectangle([(50, 710), (1030, 950)], fill=(24, 32, 47), outline=(71, 85, 105), width=3)
            summary_clean = re.sub(r"\s+", " ", summary).strip()
            summary_lines = self.wrap_text(summary_clean, max_chars_per_line=42)
            y_sum = 740
            for s_line in summary_lines[:4]:
                draw.text((80, y_sum), s_line, fill=(203, 213, 225), font=font_summary)
                y_sum += 48

        # Footer Bar with Source & Brand
        draw.rectangle([(0, 970), (width, height)], fill=(15, 23, 42))
        draw.line([(0, 970), (width, 970)], fill=(51, 65, 85), width=3)
        draw.text((60, 1000), f"Source: {source_name}", fill=(148, 163, 184), font=font_footer)
        draw.text((700, 1000), "@techcrickethub", fill=(52, 211, 153) if is_cricket else (56, 189, 248), font=font_footer)

        # Save Image
        filename = f"card_{content_id or int(time.time())}.jpg"
        file_path = os.path.join(self.output_dir, filename)
        img.save(file_path, quality=95)
        logger.info(f"Generated news graphic card: {file_path}")

        return file_path
