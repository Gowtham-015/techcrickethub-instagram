import os
import unittest
from unittest.mock import MagicMock, patch

from config import Config
from instagram_client import InstagramAPIClient
from instagram_reel_publisher import InstagramReelPublisher, PublishResult
from main import run_once, phase_15_test


class TestPhase15Requirements(unittest.TestCase):
    """Unit tests validating Phase 15 real publishing, status distinctions,

    zero-publication failure detection, workflow reliability, and Telegram isolation.
    """

    def test_verify_published_media_success(self):
        client = InstagramAPIClient(user_id="12345", access_token="mock-token-abc-123")
        client.get = MagicMock(return_value={"id": "media-9999", "media_type": "VIDEO"})

        result = client.verify_published_media("media-9999")
        self.assertTrue(result)
        client.get.assert_called_once_with("/media-9999", params={"fields": "id,media_type,timestamp,permalink"})

    def test_verify_published_media_failure(self):
        client = InstagramAPIClient(user_id="12345", access_token="mock-token-abc-123")
        client.get = MagicMock(side_effect=Exception("Media not found"))

        result = client.verify_published_media("invalid-media-id")
        self.assertFalse(result)

    def test_reel_publisher_post_publish_verification_confirmed(self):
        client = InstagramAPIClient(user_id="12345", access_token="mock-token-abc-123")
        client.post = MagicMock(side_effect=[
            {"id": "container-100"},  # Container creation
            {"id": "published-media-555"},  # Media publish
        ])
        client.get = MagicMock(side_effect=[
            {"status_code": "FINISHED"},  # Container status
            {"id": "published-media-555"},  # Post-publish verification
        ])

        publisher = InstagramReelPublisher(client=client)
        res = publisher.publish_reel(
            video_url="https://catbox.moe/test.mp4",
            caption="Real Cricket Reel",
        )

        self.assertTrue(res.success)
        self.assertEqual(res.media_id, "published-media-555")
        self.assertEqual(res.status, "PUBLISHED_CONFIRMED")

    @patch("main.InstagramAutomationEngine")
    def test_run_once_fails_when_production_publish_fails(self, mock_engine_cls):
        mock_engine = MagicMock()
        mock_engine.run_cycle.return_value = {
            "discovered": 10,
            "valid": 5,
            "duplicates": 1,
            "queued": 4,
            "published": 0,
            "failed": 4,
            "dry_run": False,
        }
        mock_engine_cls.return_value = mock_engine

        result = run_once()
        self.assertFalse(result)

    def test_workflow_file_configuration(self):
        workflow_path = os.path.join(".github", "workflows", "instagram-publisher.yml")
        self.assertTrue(os.path.exists(workflow_path))

        with open(workflow_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("cron: '7,27,47 * * * *'", content)
        self.assertIn("concurrency:", content)
        self.assertIn("group: instagram-production-publisher", content)
        self.assertIn("python main.py --run-once", content)
        self.assertNotIn('echo "INSTAGRAM MEDIA PUBLISHED"', content)

    def test_telegram_isolation(self):
        import glob
        telegram_clean = True
        bad_imp = "import " + "tele" + "bot"
        bad_from = "from " + "tele" + "bot"
        bad_ai = "import " + "ai_" + "news"

        for py_file in glob.glob("*.py"):
            with open(py_file, "r", encoding="utf-8") as f:
                code = f.read().lower()
                if bad_imp in code or bad_from in code or bad_ai in code:
                    telegram_clean = False
                    break

        self.assertTrue(telegram_clean)


if __name__ == "__main__":
    unittest.main()
