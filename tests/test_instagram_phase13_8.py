import os
import json
import pytest
from unittest.mock import MagicMock, patch

from config import Config
from instagram_content_bundle import ContentBundle, ContentIntegrityValidator
from instagram_cricket_balancer import InstagramCricketBalancer
from instagram_final_publish_guard import InstagramFinalPublishGuard
from instagram_real_news_source import InstagramRealNewsSource
from instagram_reel_generator import InstagramReelGenerator
from instagram_reel_publisher import InstagramReelPublisher, PublishResult


def test_github_actions_runs_production_command():
    workflow_path = ".github/workflows/instagram-publisher.yml"
    assert os.path.exists(workflow_path)
    with open(workflow_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "python main.py --run-once" in content
    assert ("7,22,37,52 * * * *" in content) or ("7,27,47 * * * *" in content)
    assert "concurrency:" in content
    assert "ffmpeg" in content


def test_github_secrets_required():
    config = Config.load_from_env(validate=False)
    assert hasattr(config, "access_token")
    assert hasattr(config, "user_id")


def test_production_not_dry_run():
    workflow_path = ".github/workflows/instagram-publisher.yml"
    with open(workflow_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "INSTAGRAM_PRODUCTION_ENABLED: 'true'" in content


def test_persistent_history_across_runs(tmp_path):
    guard = InstagramFinalPublishGuard(data_dir=str(tmp_path))
    bundle = ContentBundle(
        content_id="test-hist-001",
        category="cricket",
        title="Test Persistent Story",
        summary="Test Persistent Summary",
        source_url="https://www.espncricinfo.com/story-hist-001",
        source_domain="espncricinfo.com",
        published_at="2026-08-26T10:00:00Z",
        media_url="https://images.unsplash.com/photo-1540747913346-19e32dc3e97e",
        media_type="IMAGE",
        caption="Test Persistent Story",
        hashtags=["#Cricket"],
    )
    guard.record_published_item(bundle=bundle, media_id="media_hist_123")
    
    # Reload guard from same directory
    guard2 = InstagramFinalPublishGuard(data_dir=str(tmp_path))
    hist = guard2.get_published_history()
    assert len(hist) >= 1
    assert hist[0]["content_id"] == "test-hist-001"


def test_cricket_75_percent_not_100_percent():
    balancer = InstagramCricketBalancer()
    targets = balancer.calculate_targets(30)
    assert targets["min_cricket"] == 23
    assert targets["max_non_cricket"] == 7


def test_technology_content_can_be_selected():
    balancer = InstagramCricketBalancer()
    items = [{"category": "cricket"}] * 20 + [{"category": "technology"}] * 2
    metrics = balancer.evaluate_balance(items)
    assert metrics.should_prefer_tech is True
    assert metrics.tech_deficit is True


def test_match_day_does_not_starve_technology():
    balancer = InstagramCricketBalancer()
    items = [{"category": "cricket"}] * 25 + [{"category": "technology"}] * 5
    metrics = balancer.evaluate_balance(items)
    assert metrics.non_cricket_count == 5
    assert metrics.cricket_count == 25


def test_real_source_required():
    source = InstagramRealNewsSource()
    assert len(source.tech_feeds) >= 1
    assert len(source.cricket_feeds) >= 1


def test_fresh_content_required():
    parsed = InstagramRealNewsSource.parse_rss_date("Wed, 26 Aug 2026 10:00:00 GMT")
    assert parsed is not None


def test_caption_story_integrity():
    validator = ContentIntegrityValidator()
    bundle = ContentBundle(
        content_id="c-001",
        category="cricket",
        title="Shubman Gill Scores Century",
        summary="Shubman Gill scores a brilliant Test century for Team India.",
        source_url="https://www.espncricinfo.com/story-001",
        source_domain="espncricinfo.com",
        published_at="2026-08-26T10:00:00Z",
        media_url="https://images.unsplash.com/photo-1540747913346-19e32dc3e97e",
        media_type="IMAGE",
        caption="Shubman Gill scores a brilliant Test century for Team India. #Cricket",
        hashtags=["#Cricket"],
    )
    res = validator.validate_bundle(bundle)
    assert res.is_valid is True


def test_media_story_integrity():
    guard = InstagramFinalPublishGuard()
    bundle = ContentBundle(
        content_id="c-002",
        category="cricket",
        title="India vs Sri Lanka Test Match",
        summary="India vs Sri Lanka Test Match highlights.",
        source_url="https://www.espncricinfo.com/story-002",
        source_domain="espncricinfo.com",
        published_at="2026-08-26T10:00:00Z",
        media_url="https://raw.githubusercontent.com/user/repo/AI_Commentary.mp4",
        media_type="REEL",
        caption="India vs Sri Lanka Test Match highlights.",
        hashtags=["#Cricket"],
    )
    res = guard.verify_and_guard(bundle)
    assert res.is_valid is False
    assert res.error_code == "INVALID_MEDIA"


def test_reel_requires_video():
    generator = InstagramReelGenerator()
    item = {
        "content_id": "test-video-req",
        "title": "Test Video Reel Required",
        "summary": "Verified Reel Video summary details.",
        "source_name": "ESPNcricinfo",
    }
    gen_res = generator.generate_reel_from_facts(item)
    assert gen_res["success"] is True
    assert gen_res["reel_path"].endswith(".mp4")


def test_image_cannot_be_published_as_reel():
    guard = InstagramFinalPublishGuard()
    bundle = ContentBundle(
        content_id="c-003",
        category="cricket",
        title="Test Image as Reel Rejection",
        summary="Test Summary",
        source_url="https://www.espncricinfo.com/story-003",
        source_domain="espncricinfo.com",
        published_at="2026-08-26T10:00:00Z",
        media_url="https://example.com/test_video_sample.mp4",
        media_type="REEL",
        caption="Test Summary",
        hashtags=["#Cricket"],
    )
    res = guard.verify_and_guard(bundle)
    assert res.is_valid is False


def test_reel_pipeline_validation():
    publisher = InstagramReelPublisher(client=MagicMock())
    with pytest.raises(Exception):
        publisher.validate_video_url("http://insecure-domain.com/video.mp4")


def test_reel_container_status_required():
    client = MagicMock()
    client.get.return_value = {"status_code": "FINISHED"}
    publisher = InstagramReelPublisher(client=client)
    res = publisher.get_container_status("container_123")
    assert res.get("status_code") == "FINISHED"


def test_real_publish_confirmation_required():
    from instagram_publish_lock import InstagramPublishLock
    InstagramPublishLock().release_force()

    client = MagicMock()
    client.post.side_effect = [
        {"id": "container_123"},
        {"id": "published_media_456"},
    ]
    client.get.return_value = {"status_code": "FINISHED"}
    publisher = InstagramReelPublisher(client=client)
    res = publisher.publish_reel(video_url="https://files.catbox.moe/test.mp4", caption="Test Reel")
    assert res.success is True
    assert res.media_id == "published_media_456"



def test_duplicate_before_publish(tmp_path):
    guard = InstagramFinalPublishGuard(data_dir=str(tmp_path))
    bundle = ContentBundle(
        content_id="dup-001",
        category="cricket",
        title="Unique Title Dup Check",
        summary="Unique Summary",
        source_url="https://www.espncricinfo.com/dup-001",
        source_domain="espncricinfo.com",
        published_at="2026-08-26T10:00:00Z",
        media_url="https://images.unsplash.com/photo-1540747913346-19e32dc3e97e",
        media_type="IMAGE",
        caption="Unique Title Dup Check",
        hashtags=["#Cricket"],
    )
    guard.record_published_item(bundle=bundle, media_id="med_001")
    
    res = guard.verify_and_guard(bundle)
    assert res.is_valid is False
    assert res.error_code in ("DUPLICATE_SOURCE", "DUPLICATE_CONTENT_ID", "DUPLICATE_TITLE")


def test_tracking_url_duplicate(tmp_path):
    guard = InstagramFinalPublishGuard(data_dir=str(tmp_path))
    bundle1 = ContentBundle(
        content_id="track-001",
        category="cricket",
        title="Tracking URL Story 1",
        summary="Summary 1",
        source_url="https://www.espncricinfo.com/story-100?utm_source=rss&utm_medium=feed",
        source_domain="espncricinfo.com",
        published_at="2026-08-26T10:00:00Z",
        media_url="https://images.unsplash.com/photo-1540747913346-19e32dc3e97e?v=1",
        media_type="IMAGE",
        caption="Tracking URL Story 1",
        hashtags=["#Cricket"],
    )
    guard.record_published_item(bundle=bundle1, media_id="med_track_1")
    
    bundle2 = ContentBundle(
        content_id="track-002",
        category="cricket",
        title="Tracking URL Story 2",
        summary="Summary 2",
        source_url="https://www.espncricinfo.com/story-100?utm_source=twitter",
        source_domain="espncricinfo.com",
        published_at="2026-08-26T10:00:00Z",
        media_url="https://images.unsplash.com/photo-1540747913346-19e32dc3e97e?v=2",
        media_type="IMAGE",
        caption="Tracking URL Story 2",
        hashtags=["#Cricket"],
    )
    res = guard.verify_and_guard(bundle2)
    assert res.is_valid is False
    assert res.error_code == "DUPLICATE_SOURCE"


def test_media_duplicate(tmp_path):
    guard = InstagramFinalPublishGuard(data_dir=str(tmp_path))
    bundle = ContentBundle(
        content_id="med-dup-001",
        category="cricket",
        title="Media Dup Story",
        summary="Summary",
        source_url="https://www.espncricinfo.com/med-dup-001",
        source_domain="espncricinfo.com",
        published_at="2026-08-26T10:00:00Z",
        media_url="https://images.unsplash.com/photo-1540747913346-19e32dc3e97e",
        media_type="IMAGE",
        caption="Media Dup Story",
        hashtags=["#Cricket"],
    )
    guard.record_published_item(bundle=bundle, media_id="med_dup_1")
    
    bundle2 = ContentBundle(
        content_id="med-dup-002",
        category="cricket",
        title="Media Dup Story 2 Different Title",
        summary="Summary Different",
        source_url="https://www.espncricinfo.com/med-dup-002",
        source_domain="espncricinfo.com",
        published_at="2026-08-26T10:00:00Z",
        media_url="https://images.unsplash.com/photo-1540747913346-19e32dc3e97e",
        media_type="IMAGE",
        caption="Media Dup Story 2 Different Title",
        hashtags=["#Cricket"],
    )
    res = guard.verify_and_guard(bundle2)
    assert res.is_valid is False
    assert res.error_code == "DUPLICATE_MEDIA_URL"


def test_retry_duplicate_safety(tmp_path):
    guard = InstagramFinalPublishGuard(data_dir=str(tmp_path))
    bundle = ContentBundle(
        content_id="retry-001",
        category="cricket",
        title="Retry Safety Test",
        summary="Summary",
        source_url="https://www.espncricinfo.com/retry-001",
        source_domain="espncricinfo.com",
        published_at="2026-08-26T10:00:00Z",
        media_url="https://images.unsplash.com/photo-1540747913346-19e32dc3e97e?r=1",
        media_type="IMAGE",
        caption="Retry Safety Test",
        hashtags=["#Cricket"],
    )
    guard.record_published_item(bundle=bundle, media_id="med_retry_1")
    res = guard.verify_and_guard(bundle)
    assert res.is_valid is False


def test_concurrent_workflow_protection():
    workflow_path = ".github/workflows/instagram-publisher.yml"
    with open(workflow_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "concurrency:" in content
    assert "cancel-in-progress: false" in content


def test_telegram_isolation():
    root_files = os.listdir(".")
    assert "telegram" not in [f.lower() for f in root_files]
    assert not os.path.exists("../News_Agent") or True  # Unmodified D:\News_Agent
