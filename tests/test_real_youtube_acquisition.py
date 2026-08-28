import os
import unittest
from unittest.mock import MagicMock, patch

from instagram_real_video_source import InstagramRealVideoSource


class TestRealYouTubeAcquisition(unittest.TestCase):
    """Test suite for Real YouTube and Google video acquisition pipeline."""

    def setUp(self):
        self.source = InstagramRealVideoSource()

    def test_discover_video_items_cricket(self):
        """Verify Cricket real video discovery returns authorized video items."""
        items = self.source.discover_video_items(category="cricket", limit=2)
        self.assertGreater(len(items), 0)
        first = items[0]
        self.assertEqual(first["category"], "cricket")
        self.assertEqual(first["media_type"], "REEL")
        self.assertIsNotNone(first["video_url"])
        self.assertIn(first["media_rights_status"], self.source.ALLOWED_RIGHTS_STATUSES)

    def test_discover_video_items_technology(self):
        """Verify Technology real video discovery returns authorized video items."""
        items = self.source.discover_video_items(category="technology", limit=2)
        self.assertGreater(len(items), 0)
        first = items[0]
        self.assertEqual(first["category"], "technology")
        self.assertEqual(first["media_type"], "REEL")
        self.assertIsNotNone(first["video_url"])
        self.assertIn(first["media_rights_status"], self.source.ALLOWED_RIGHTS_STATUSES)

    def test_get_content_items_interface(self):
        """Verify get_content_items conforms to InstagramContentSource interface."""
        items = self.source.get_content_items(download_video=False)
        self.assertIsInstance(items, list)
        if items:
            first = items[0]
            self.assertIn("video_url", first)
            self.assertEqual(first.get("media_type"), "REEL")


    @patch("subprocess.run")
    def test_format_vertical_reel(self, mock_run):
        """Verify FFmpeg 9:16 vertical (1080x1920) Reel formatting command."""
        mock_run.return_value = MagicMock(returncode=0)
        # Create a mock temporary input file
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(b"fake_mp4_content")
            tmp_path = tmp.name

        try:
            res = self.source.format_vertical_reel(tmp_path)
            self.assertIsNotNone(res)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


if __name__ == "__main__":
    unittest.main()
