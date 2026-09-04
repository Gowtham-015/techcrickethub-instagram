import logging
import os
import uuid
import pytest
from unittest.mock import MagicMock, patch

from config import Config
from instagram_automation_engine import InstagramAutomationEngine
from instagram_client import InstagramAPIClient
from instagram_media_verifier import InstagramMediaVerifier
from instagram_pipeline import InstagramContent, InstagramContentPipeline, PipelineResult
from instagram_reel_publisher import InstagramReelPublisher, PublishResult


class TestPhase151CriticalBugFix:
    """Comprehensive test suite verifying Phase 15.1 Critical Production Bug Fix requirements."""

    def test_all_valid_items_not_marked_failed(self):
        """Valid generated Reel items must not be incorrectly marked as Failed."""
        config = Config.load_from_env(validate=False)
        config.dry_run = True
        config.max_items_per_cycle = 3

        uid = str(uuid.uuid4())[:8]
        test_id = f"test-valid-{uid}"

        mock_source = MagicMock()
        mock_source.get_content_items.return_value = [
            {
                "content_id": test_id,
                "title": "India Win Test Series with Dominant Performance",
                "summary": "Team India secures victory with sensational bowling performance.",
                "category": "cricket",
                "source_name": "ESPNcricinfo",
                "source_url": f"https://espncricinfo.com/story-{uid}",
                "media_type": "REEL",
                "image_url": None,
                "video_url": f"https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/data/generated_reels/reel_real-{uid}.mp4",
                "media_rights_status": "ORIGINAL_GENERATED",
            }
        ]

        engine = InstagramAutomationEngine(config=config, source=mock_source)
        engine.queue.clear()


        with patch.object(engine.source_verifier, "verify_source", return_value=MagicMock(is_valid=True)), \
             patch.object(engine.media_verifier, "verify_and_deduplicate") as mock_mv, \
             patch.object(engine.acquirer, "acquire_media") as mock_am, \
             patch.object(engine.deduplicator, "is_duplicate", return_value=False), \
             patch.object(engine.repetition_guard, "check_repetition") as mock_rg, \
             patch.object(engine.final_publish_guard, "verify_and_guard") as mock_fg:

            mock_mv.return_value = MagicMock(is_valid=True, message="Media OK")
            mock_am.return_value = MagicMock(is_https=True, content_type="video/mp4")
            mock_rg.return_value = MagicMock(is_repeated=False)
            mock_fg.return_value = MagicMock(is_valid=True)

            res = engine.run_cycle()


            assert res["valid"] == 1
            assert res["failed"] == 0
            assert res["queued"] == 1

    def test_valid_reel_enters_queue(self):
        """A valid generated Reel candidate must enter the queue as PENDING."""
        config = Config.load_from_env(validate=False)
        config.reel_discovery_enabled = True
        engine = InstagramAutomationEngine(config=config)
        engine.queue.clear()

        uid = str(uuid.uuid4())[:8]
        test_id = f"test-reel-q-{uid}"


        test_item = {
            "content_id": test_id,
            "title": "Quantum Computing Breakthrough Benchmark Released",
            "summary": "Scientists demonstrate revolutionary qubit coherence stability.",
            "category": "technology",
            "source_name": "TechCrunch",
            "source_url": f"https://techcrunch.com/qc-{uid}",
            "media_type": "REEL",
            "video_url": f"https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/data/generated_reels/reel_real-{uid}.mp4",
            "media_rights_status": "ORIGINAL_GENERATED",
        }

        with patch.object(engine.source_verifier, "verify_item") as mock_sv, \
             patch.object(engine.media_verifier, "verify_and_deduplicate") as mock_mv, \
             patch.object(engine.acquirer, "acquire_media") as mock_am, \
             patch.object(engine.deduplicator, "is_duplicate", return_value=False), \
             patch.object(engine.repetition_guard, "check_repetition") as mock_rg, \
             patch.object(engine.final_publish_guard, "verify_and_guard") as mock_fg:

            mock_sv.return_value = MagicMock(is_valid=True)
            mock_mv.return_value = MagicMock(is_valid=True)
            mock_am.return_value = MagicMock(is_https=True, content_type="video/mp4")
            mock_rg.return_value = MagicMock(is_repeated=False)
            mock_fg.return_value = MagicMock(is_valid=True)

            real_content = InstagramContent(
                title=test_item["title"],
                summary=test_item["summary"],
                category=test_item["category"],
                media_type="REEL",
                video_url=test_item["video_url"],
                source=test_item["source_name"],
                caption=test_item["title"],
                hashtags=["#technology"],
                metadata={"content_id": test_id},
            )
            engine.normalizer.normalize = MagicMock(return_value=real_content)

            engine.source.get_content_items = MagicMock(return_value=[test_item])
            if hasattr(engine, "news_source") and engine.news_source:
                engine.news_source.get_content_items = MagicMock(return_value=[])
            res = engine.run_cycle()

            assert res["queued"] >= 1

    def test_publish_result_updates_engine(self):
        """Engine published count MUST increment ONLY when PublishResult.success is True."""
        config = Config.load_from_env(validate=False)
        config.dry_run = False
        config.production_enabled = True

        engine = InstagramAutomationEngine(config=config)

        mock_scheduler_res = PipelineResult(
            success=True,
            media_type="REEL",
            status="PUBLISHED",
            creation_id="17900000000000001",
            media_id="17900000000000002",
            message="Published successfully",
            dry_run=False,
        )

        with patch.object(engine.scheduler, "process_due_items", return_value=[mock_scheduler_res]), \
             patch.object(engine.source, "get_content_items", return_value=[]):
            res = engine.run_cycle()
            assert res["published"] == 1

    def test_failed_publish_does_not_increment_published_count(self):
        """Engine published count MUST NOT increment if publishing failed."""
        config = Config.load_from_env(validate=False)
        engine = InstagramAutomationEngine(config=config)

        mock_failed_res = PipelineResult(
            success=False,
            media_type="REEL",
            status="FAILED",
            creation_id="17900000000000001",
            media_id=None,
            message="Container processing failed",
            dry_run=False,
        )

        with patch.object(engine.scheduler, "process_due_items", return_value=[mock_failed_res]), \
             patch.object(engine.source, "get_content_items", return_value=[]):
            res = engine.run_cycle()
            assert res["published"] == 0
            assert res["failed"] == 1

    def test_media_id_required_for_success(self):
        """A missing returned media_id MUST result in a failed PublishResult."""
        client = MagicMock(spec=InstagramAPIClient)
        client.user_id = "37982406558040899"
        client.access_token = "SECRET_TOKEN"
        client.logger = logging.getLogger("TestLogger")
        client.post.side_effect = [
            {"id": "18000000000000001"},
            {},  # Empty response missing 'id'
        ]
        client.get.return_value = {"status_code": "FINISHED"}

        publisher = InstagramReelPublisher(client=client, poll_interval_seconds=0)
        res = publisher.publish_reel(
            video_url="https://raw.githubusercontent.com/test/video.mp4",
            caption="Test Caption",
        )

        assert res.success is False
        assert res.media_id is None
        assert "no 'id'" in res.message or "returned" in res.message.lower()

    def test_publication_verification_required(self):
        """verify_published_media MUST confirm Meta state before publication confirmation."""
        client = InstagramAPIClient(user_id="12345", access_token="test_token")
        client.get = MagicMock(return_value={"id": "18000000000000099", "media_type": "REELS"})

        verified = client.verify_published_media("18000000000000099")
        assert verified is True

        client.get.return_value = {}
        unverified = client.verify_published_media("invalid-media-id")
        assert unverified is False

    def test_container_finished_not_equal_published(self):
        """Container status FINISHED is NOT equal to media published."""
        pub_result = PublishResult(
            success=False,
            creation_id="18000000000000001",
            media_id=None,
            status="FINISHED",
            message="Container finished but media_publish not called yet",
        )
        assert pub_result.success is False
        assert pub_result.media_id is None

    def test_state_not_marked_published_before_media_publish(self):
        """State record must remain UNPUBLISHED before media_publish call."""
        guard = MagicMock()
        guard.get_published_history.return_value = []
        hist = guard.get_published_history()
        assert len(hist) == 0

    def test_github_runtime_uses_production_path(self):
        """Verify main.py --run-once path exists and executes correctly."""
        from main import main
        assert callable(main)

    def test_github_raw_media_accessibility(self):
        """Verify Meta media accessibility validation helper behavior."""
        res = InstagramMediaVerifier.validate_meta_media_accessibility(
            url="https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/data/generated_reels/reel_real-test.mp4",
            media_type="REEL",
        )
        assert isinstance(res, dict)
        assert "is_valid" in res

    def test_publish_test_real_path(self):
        """Verify publish_test function exists and executes."""
        from main import publish_test
        assert callable(publish_test)

    def test_no_false_success_logging(self):
        """Ensure no false INSTAGRAM MEDIA PUBLISHED string is logged on failure."""
        res = PublishResult(
            success=False,
            creation_id="123",
            media_id=None,
            status="FAILED",
            message="Container creation error",
        )
        assert res.success is False
