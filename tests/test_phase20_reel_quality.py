import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from instagram_reel_quality_engine import InstagramReelQualityEngine, ReelQualityResult


class TestPhase20ReelQualityEngine(unittest.TestCase):
    """Unit tests for Phase 20 Production Reel Quality Engine."""

    def setUp(self):
        self.engine = InstagramReelQualityEngine()

    def test_valid_reel_quality_passes(self):
        """Verify standard 9:16 vertical 1080x1920 reel passes validation."""
        meta = {
            "width": 1080,
            "height": 1920,
            "fps": 30.0,
            "duration": 15.0,
            "has_audio": True,
            "audio_codec": "aac",
        }
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2mp41" + b"\x00" * 2000)
            tmp_path = f.name

        try:
            res = self.engine.validate_reel_quality(tmp_path, item_metadata=meta)
            self.assertTrue(res.is_valid)
            self.assertEqual(res.error_code, "SUCCESS")
            self.assertEqual(res.width, 1080)
            self.assertEqual(res.height, 1920)
            self.assertGreaterEqual(res.quality_score, 80.0)
            self.assertTrue(res.has_audio)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_invalid_aspect_ratio_rejection(self):
        """Verify horizontal video (1920x1080) is rejected for Reels."""
        meta = {
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "duration": 15.0,
        }
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 2000)
            tmp_path = f.name

        try:
            res = self.engine.validate_reel_quality(tmp_path, item_metadata=meta)
            self.assertFalse(res.is_valid)
            self.assertEqual(res.error_code, "INVALID_ASPECT_RATIO")
            self.assertIn("Horizontal/square video orientation detected", "; ".join(res.issues))
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_invalid_duration_rejection(self):
        """Verify duration under 3.0s or over 90.0s is rejected."""
        meta_short = {"width": 1080, "height": 1920, "fps": 30.0, "duration": 1.5}
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 2000)
            tmp_path = f.name

        try:
            res = self.engine.validate_reel_quality(tmp_path, item_metadata=meta_short)
            self.assertFalse(res.is_valid)
            self.assertIn("duration", "; ".join(res.issues).lower())
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_black_video_rejection(self):
        """Verify pure black/empty video content is rejected."""
        meta = {"width": 1080, "height": 1920, "fps": 30.0, "duration": 10.0, "is_black_video": True}
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 2000)
            tmp_path = f.name

        try:
            res = self.engine.validate_reel_quality(tmp_path, item_metadata=meta)
            self.assertFalse(res.is_valid)
            self.assertEqual(res.error_code, "BLACK_VIDEO_REJECTED")
            self.assertTrue(res.is_black_video)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_static_image_video_rejection(self):
        """Verify image-to-video conversion or 1-frame static video is rejected."""
        meta = {"width": 1080, "height": 1920, "fps": 30.0, "duration": 10.0, "converted_from_image": True}
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 2000)
            tmp_path = f.name

        try:
            res = self.engine.validate_reel_quality(tmp_path, item_metadata=meta)
            self.assertFalse(res.is_valid)
            self.assertEqual(res.error_code, "IMAGE_TO_VIDEO_REJECTED")
            self.assertTrue(res.is_static_image_video)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_stretched_video_detection(self):
        """Verify video with severe SAR aspect ratio distortion is flagged."""
        meta = {"width": 1080, "height": 1920, "fps": 30.0, "duration": 10.0, "is_stretched": True}
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 2000)
            tmp_path = f.name

        try:
            res = self.engine.validate_reel_quality(tmp_path, item_metadata=meta)
            self.assertTrue(res.is_stretched)
            self.assertIn("Stretched video ratio", "; ".join(res.issues))
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_safe_zone_text_violation(self):
        """Verify text overlays placed outside Instagram safe zones are flagged."""
        meta = {"width": 1080, "height": 1920, "fps": 30.0, "duration": 10.0}
        overlays = [{"y": 50, "height": 100, "text": "Unreadable top header"}]  # y=50 breaks top 150px safe zone
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 2000)
            tmp_path = f.name

        try:
            res = self.engine.validate_reel_quality(tmp_path, item_metadata=meta, text_overlays=overlays)
            self.assertTrue(res.has_safe_zone_text_violation)
            self.assertIn("safe zones", "; ".join(res.issues))
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_synthetic_sports_footage_rejection(self):
        """Verify synthetic/AI sports footage flag is strictly rejected."""
        meta = {"is_synthetic": True}
        res = self.engine.validate_reel_quality("dummy.mp4", item_metadata=meta)
        self.assertFalse(res.is_valid)
        self.assertEqual(res.error_code, "SYNTHETIC_FOOTAGE_REJECTED")


if __name__ == "__main__":
    unittest.main()
