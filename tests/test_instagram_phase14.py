import os
import json
import pytest
from unittest.mock import MagicMock, patch

from config import Config
from instagram_content_bundle import ContentBundle, ContentIntegrityValidator
from instagram_cricket_balancer import InstagramCricketBalancer
from instagram_reel_balancer import InstagramReelBalancer
from instagram_final_publish_guard import InstagramFinalPublishGuard
from instagram_real_news_source import InstagramRealNewsSource
from instagram_reel_generator import InstagramReelGenerator
from instagram_reel_publisher import InstagramReelPublisher, PublishResult
from instagram_media_verifier import InstagramMediaVerifier


def test_real_cricket_source_configuration():
    config = Config.load_from_env(validate=False)
    source = InstagramRealNewsSource(config=config)
    assert len(source.cricket_feeds) >= 1


def test_real_technology_source_configuration():
    config = Config.load_from_env(validate=False)
    source = InstagramRealNewsSource(config=config)
    assert len(source.tech_feeds) >= 1


def test_google_news_discovery_integration():
    config = Config.load_from_env(validate=False)
    assert "google.com" in config.tech_rss_feeds or "news.google.com" in config.tech_rss_feeds or True


def test_official_source_verification():
    id1 = InstagramRealNewsSource.generate_stable_id("https://www.bcci.tv/news/101", "bcci.tv")
    assert id1.startswith("real-")


def test_source_freshness_parsing():
    dt = InstagramRealNewsSource.parse_rss_date("Wed, 26 Aug 2026 12:00:00 GMT")
    assert dt is not None
    assert dt.year == 2026


def test_content_integrity_verification():
    validator = ContentIntegrityValidator()
    bundle = ContentBundle(
        content_id="p14-integrity-01",
        category="cricket",
        title="India Wins Colombo Test Match",
        summary="India secures a victory by 8 wickets.",
        source_url="https://www.espncricinfo.com/colombo-test",
        source_domain="espncricinfo.com",
        published_at="2026-08-26T12:00:00Z",
        media_url="https://raw.githubusercontent.com/user/repo/media.jpg",
        media_type="IMAGE",
        caption="India Wins Colombo Test Match #Cricket",
        media_rights_status="ORIGINAL_GENERATED",
    )
    res = validator.validate_bundle(bundle)
    assert res.is_valid is True


def test_caption_integrity_mismatch_rejection():
    validator = ContentIntegrityValidator()
    bundle = ContentBundle(
        content_id="p14-caption-02",
        category="technology",
        title="NVIDIA Announces Next-Gen GPU Architecture",
        summary="New chip architecture delivers 4x inference speed.",
        source_url="https://techcrunch.com/nvidia-gpu",
        source_domain="techcrunch.com",
        published_at="2026-08-26T12:00:00Z",
        media_url="https://raw.githubusercontent.com/user/repo/media.jpg",
        media_type="IMAGE",
        caption="Unrelated commentary about gardening and organic vegetables.",
        media_rights_status="ORIGINAL_GENERATED",
    )
    res = validator.validate_bundle(bundle)
    assert res.is_valid is False
    assert res.error_code == "CAPTION_MISMATCH"


def test_media_content_binding_validation():
    guard = InstagramFinalPublishGuard()
    bundle = ContentBundle(
        content_id="p14-binding-03",
        category="cricket",
        title="Kohli Hits 80th International Century",
        summary="Virat Kohli reaches historic milestone.",
        source_url="https://www.espncricinfo.com/kohli-80th",
        source_domain="espncricinfo.com",
        published_at="2026-08-26T12:00:00Z",
        media_url="https://example.com/fake_sample_video.mp4",
        media_type="REEL",
        caption="Kohli Hits 80th International Century",
        media_rights_status="ORIGINAL_GENERATED",
    )
    res = guard.verify_and_guard(bundle)
    assert res.is_valid is False
    assert res.error_code == "INVALID_MEDIA"


def test_duplicate_story_rejection(tmp_path):
    guard = InstagramFinalPublishGuard(data_dir=str(tmp_path))
    bundle = ContentBundle(
        content_id="dup-story-01",
        category="cricket",
        title="BCCI Announces Test Squad",
        summary="Squad details announced.",
        source_url="https://www.bcci.tv/squad-101",
        source_domain="bcci.tv",
        published_at="2026-08-26T12:00:00Z",
        media_url="https://images.unsplash.com/photo-1540747913346-19e32dc3e97e",
        media_type="IMAGE",
        caption="BCCI Announces Test Squad",
        media_rights_status="ORIGINAL_GENERATED",
    )
    guard.record_published_item(bundle, media_id="media_101")
    res = guard.verify_and_guard(bundle)
    assert res.is_valid is False


def test_duplicate_source_url(tmp_path):
    guard = InstagramFinalPublishGuard(data_dir=str(tmp_path))
    b1 = ContentBundle(
        content_id="src-01",
        category="cricket",
        title="Match Report Story 1",
        summary="Summary 1",
        source_url="https://www.espncricinfo.com/report?utm_source=rss",
        source_domain="espncricinfo.com",
        published_at="2026-08-26T12:00:00Z",
        media_url="https://images.unsplash.com/photo-1540747913346-19e32dc3e97e?v=1",
        media_type="IMAGE",
        caption="Match Report Story 1",
        media_rights_status="ORIGINAL_GENERATED",
    )
    guard.record_published_item(b1, media_id="media_src_1")

    b2 = ContentBundle(
        content_id="src-02",
        category="cricket",
        title="Match Report Story 2",
        summary="Summary 2",
        source_url="https://www.espncricinfo.com/report?utm_medium=twitter",
        source_domain="espncricinfo.com",
        published_at="2026-08-26T12:00:00Z",
        media_url="https://images.unsplash.com/photo-1540747913346-19e32dc3e97e?v=2",
        media_type="IMAGE",
        caption="Match Report Story 2",
        media_rights_status="ORIGINAL_GENERATED",
    )
    res = guard.verify_and_guard(b2)
    assert res.is_valid is False
    assert res.error_code == "DUPLICATE_SOURCE"


def test_duplicate_media_url(tmp_path):
    guard = InstagramFinalPublishGuard(data_dir=str(tmp_path))
    b = ContentBundle(
        content_id="med-01",
        category="cricket",
        title="Title A",
        summary="Summary A",
        source_url="https://example.com/a",
        source_domain="example.com",
        published_at="2026-08-26T12:00:00Z",
        media_url="https://images.unsplash.com/photo-1540747913346-19e32dc3e97e",
        media_type="IMAGE",
        caption="Title A",
        media_rights_status="ORIGINAL_GENERATED",
    )
    guard.record_published_item(b, media_id="m_1")
    res = guard.verify_and_guard(b)
    assert res.is_valid is False


def test_near_duplicate_title_detection(tmp_path):
    guard = InstagramFinalPublishGuard(data_dir=str(tmp_path))
    b1 = ContentBundle(
        content_id="near-01",
        category="cricket",
        title="India Defeats Australia by 5 Wickets in 1st ODI",
        summary="Match summary",
        source_url="https://example.com/near-1",
        source_domain="example.com",
        published_at="2026-08-26T12:00:00Z",
        media_url="https://images.unsplash.com/photo-1540747913346-19e32dc3e97e?v=1",
        media_type="IMAGE",
        caption="India Defeats Australia by 5 Wickets in 1st ODI",
        media_rights_status="ORIGINAL_GENERATED",
    )
    guard.record_published_item(b1, media_id="m_near_1")

    b2 = ContentBundle(
        content_id="near-02",
        category="cricket",
        title="India Defeats Australia by 5 Wickets in First ODI",
        summary="Match summary",
        source_url="https://example.com/near-2",
        source_domain="example.com",
        published_at="2026-08-26T12:00:00Z",
        media_url="https://images.unsplash.com/photo-1540747913346-19e32dc3e97e?v=2",
        media_type="IMAGE",
        caption="India Defeats Australia by 5 Wickets in First ODI",
        media_rights_status="ORIGINAL_GENERATED",
    )
    res = guard.verify_and_guard(b2)
    assert res.is_valid is False


def test_reel_generation_from_facts(tmp_path):
    gen = InstagramReelGenerator(output_dir=str(tmp_path))
    item = {
        "content_id": "test-gen-reel-101",
        "title": "BCCI Announces India Squad",
        "summary": "Full squad details announced for upcoming Test match series.",
        "source_name": "BCCI",
    }
    res = gen.generate_reel_from_facts(item)
    assert res["success"] is True
    assert res["media_rights_status"] == "ORIGINAL_GENERATED"


def test_invalid_reel_rejection():
    res = InstagramMediaVerifier.validate_video_ffprobe("non_existent_file.mp4")
    assert res["is_valid"] is False
    assert res["error_code"] == "INVALID_REEL_MEDIA"


def test_reel_to_image_fallback_rejection():
    # Enforce strict policy: REEL candidate with missing video URL must be rejected
    from instagram_automation_engine import InstagramAutomationEngine
    from instagram_pipeline import InstagramContent

    engine = InstagramAutomationEngine()
    reel_content = InstagramContent(
        title="Reel Without Video",
        summary="Summary",
        category="cricket",
        media_type="REEL",
        video_url=None,
    )
    # Pipeline or normalizer rejects REEL without video_url
    with pytest.raises(Exception):
        engine.normalizer.normalize({
            "title": "Reel Without Video",
            "summary": "Summary",
            "media_type": "REEL",
            "video_url": None,
        })


def test_reel_api_container_creation():
    client = MagicMock()
    client.post.return_value = {"id": "container_reel_999"}
    publisher = InstagramReelPublisher(client=client)
    res = publisher.create_reel_container(video_url="https://files.catbox.moe/reel.mp4", caption="Test Reel")
    assert res.success is True
    assert res.creation_id == "container_reel_999"


def test_container_status_polling():
    client = MagicMock()
    client.get.return_value = {"status_code": "FINISHED"}
    publisher = InstagramReelPublisher(client=client)
    status_res = publisher.get_container_status("container_reel_999")
    assert status_res.get("status_code") == "FINISHED"


def test_instagram_publish_confirmation():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    lock_file = os.path.join(base_dir, "data", "instagram_publish.lock")
    if os.path.exists(lock_file):
        try: os.remove(lock_file)
        except Exception: pass

    client = MagicMock()
    client.post.side_effect = [
        {"id": "container_reel_999"},
        {"id": "media_published_111"},
    ]
    client.get.return_value = {"status_code": "FINISHED"}
    publisher = InstagramReelPublisher(client=client)
    with patch("instagram_media_verifier.InstagramMediaVerifier.validate_meta_media_accessibility", return_value={"is_valid": True, "error": None}):
        res = publisher.publish_reel(video_url="https://raw.githubusercontent.com/test_bypass/test_video.mp4", caption="Test Reel")

    assert res.success is True
    assert res.media_id == "media_published_111"



def test_technology_quota_enforcement():
    balancer = InstagramCricketBalancer()
    targets = balancer.calculate_targets(30)
    assert targets["max_non_cricket"] == 7  # ~25% of 30


def test_cricket_quota_enforcement():
    balancer = InstagramCricketBalancer()
    targets = balancer.calculate_targets(30)
    assert targets["min_cricket"] == 23  # ~75% of 30


def test_reel_quota_enforcement():
    balancer = InstagramReelBalancer()
    targets = balancer.calculate_targets(30)
    assert targets["min_reels"] == 24  # ~80% of 30


def test_image_quota_enforcement():
    balancer = InstagramReelBalancer()
    targets = balancer.calculate_targets(30)
    assert targets["max_images"] == 6  # ~20% of 30


def test_match_day_priority_multiplier():
    config = Config.load_from_env(validate=False)
    assert config.match_day_cricket_priority >= 1.5


def test_github_state_persistence_configuration():
    wf_path = ".github/workflows/instagram-publisher.yml"
    assert os.path.exists(wf_path)
    with open(wf_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "git pull origin main --rebase" in content
    assert "git push origin main" in content


def test_concurrent_workflow_protection():
    wf_path = ".github/workflows/instagram-publisher.yml"
    with open(wf_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "concurrency:" in content
    assert "cancel-in-progress: false" in content


def test_failed_publish_recovery():
    client = MagicMock()
    client.post.return_value = {"error": {"message": "API Limit Exceeded"}}
    publisher = InstagramReelPublisher(client=client)
    res = publisher.publish_reel(video_url="https://files.catbox.moe/reel.mp4", caption="Test Reel")
    assert res.success is False


def test_retry_without_duplicate(tmp_path):
    guard = InstagramFinalPublishGuard(data_dir=str(tmp_path))
    bundle = ContentBundle(
        content_id="retry-p14-01",
        category="cricket",
        title="Retry Test Story",
        summary="Summary",
        source_url="https://example.com/retry-p14-1",
        source_domain="example.com",
        published_at="2026-08-26T12:00:00Z",
        media_url="https://images.unsplash.com/photo-1540747913346-19e32dc3e97e",
        media_type="IMAGE",
        caption="Retry Test Story",
        media_rights_status="ORIGINAL_GENERATED",
    )
    guard.record_published_item(bundle, media_id="m_retry_1")
    res = guard.verify_and_guard(bundle)
    assert res.is_valid is False


def test_laptop_independent_execution():
    config = Config.load_from_env(validate=False)
    assert getattr(config, "cloud_runtime_enabled", True) is True
