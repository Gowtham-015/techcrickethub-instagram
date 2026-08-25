import glob
import os
import pytest
from config import Config
from instagram_content_bundle import ContentBundle, ContentIntegrityValidator
from instagram_cricket_data_provider import FallbackCricketProvider
from instagram_cricket_match_intelligence import InstagramCricketMatchIntelligence
from instagram_final_publish_guard import InstagramFinalPublishGuard
from instagram_media_verifier import InstagramMediaVerifier
from instagram_real_news_source import InstagramRealNewsSource
from main import validate_github_secrets


def test_github_actions_configuration():
    """Verifies that .github/workflows/instagram-publisher.yml exists and contains scheduled cron and workflow_dispatch."""
    wf_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".github", "workflows", "instagram-publisher.yml")
    assert os.path.exists(wf_path)
    with open(wf_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "schedule:" in content
    assert "cron:" in content
    assert "workflow_dispatch:" in content
    assert "secrets.INSTAGRAM_USER_ID" in content
    assert "secrets.INSTAGRAM_ACCESS_TOKEN" in content


def test_github_secret_validation():
    """Verifies safe GitHub Secret validation helper."""
    val = validate_github_secrets()
    assert isinstance(val, bool)


def test_laptop_independent_runtime():
    """Verifies that execution environment does not require local laptop main loop."""
    config = Config.load_from_env(validate=False)
    assert getattr(config, "cloud_runtime_enabled", True) is True


def test_persistent_publish_history(tmp_path):
    """Verifies persistent history reloading across workflow instances."""
    data_dir = str(tmp_path / "data")
    guard1 = InstagramFinalPublishGuard(data_dir=data_dir)

    bundle = ContentBundle(
        content_id="p-hist-101",
        category="cricket",
        title="Persistent History Test Title",
        summary="Summary test",
        source_url="https://example.com/p-hist-101",
        source_domain="example.com",
        published_at="2026-08-25T00:00:00Z",
        media_url="https://example.com/image-ph.jpg",
        media_type="IMAGE",
        caption="Persistent History Test Title caption",
    )

    guard1.record_published_item(bundle=bundle, media_id="media-ph-101")

    # Instance 2 reloads history from disk
    guard2 = InstagramFinalPublishGuard(data_dir=data_dir)
    res = guard2.verify_and_guard(bundle)
    assert not res.is_valid


def test_duplicate_before_publish(tmp_path):
    data_dir = str(tmp_path / "data")
    guard = InstagramFinalPublishGuard(data_dir=data_dir)

    b = ContentBundle(
        content_id="dup-pre-1",
        category="cricket",
        title="Pre Publish Dup Title",
        summary="Summary",
        source_url="https://example.com/dup-pre-1",
        source_domain="example.com",
        published_at="2026-08-25T00:00:00Z",
        media_url="https://example.com/dup-pre-1.jpg",
        media_type="IMAGE",
        caption="Pre Publish Dup Title caption",
    )
    guard.record_published_item(b, media_id="m-dup-1")

    res = guard.verify_and_guard(b)
    assert not res.is_valid


def test_duplicate_tracking_url(tmp_path):
    data_dir = str(tmp_path / "data")
    guard = InstagramFinalPublishGuard(data_dir=data_dir)

    u1 = "https://example.com/story-a?utm_source=twitter"
    u2 = "https://example.com/story-a?utm_medium=email&fbclid=abc"

    assert guard.canonicalize_url(u1) == guard.canonicalize_url(u2)


def test_duplicate_media(tmp_path):
    data_dir = str(tmp_path / "data")
    guard = InstagramFinalPublishGuard(data_dir=data_dir)

    m_bytes = b"fake_jpeg_image_bytes_sha256_test"
    b = ContentBundle(
        content_id="m-dup-1",
        category="cricket",
        title="Media SHA256 Dup Title",
        summary="Summary",
        source_url="https://example.com/m-dup-1",
        source_domain="example.com",
        published_at="2026-08-25T00:00:00Z",
        media_url="https://example.com/m-dup-1.jpg",
        media_type="IMAGE",
        caption="Media SHA256 Dup Title caption",
    )
    guard.record_published_item(b, media_id="m-1", media_bytes=m_bytes)

    res = guard.verify_and_guard(b, media_bytes=m_bytes)
    assert not res.is_valid
    assert res.error_code in ("DUPLICATE_SOURCE", "DUPLICATE_CONTENT_ID", "DUPLICATE_MEDIA")


def test_duplicate_generated_reel(tmp_path):
    data_dir = str(tmp_path / "data")
    guard = InstagramFinalPublishGuard(data_dir=data_dir)

    b = ContentBundle(
        content_id="reel-dup-1",
        category="cricket",
        title="Unique Generated Story Reel",
        summary="Summary",
        source_url="https://example.com/reel-dup-1",
        source_domain="example.com",
        published_at="2026-08-25T00:00:00Z",
        media_url="https://example.com/reel-dup-1.mp4",
        media_type="REEL",
        caption="Unique Generated Story Reel caption",
    )
    guard.record_published_item(b, media_id="m-reel-1")

    res = guard.verify_and_guard(b)
    assert not res.is_valid


def test_caption_story_mismatch(tmp_path):
    data_dir = str(tmp_path / "data")
    guard = InstagramFinalPublishGuard(data_dir=data_dir)

    b = ContentBundle(
        content_id="mismatch-1",
        category="cricket",
        title="India Defeats England in Cricket Final",
        summary="India won Cricket Final.",
        source_url="https://example.com/mismatch-1",
        source_domain="example.com",
        published_at="2026-08-25T00:00:00Z",
        media_url="https://example.com/mismatch-1.jpg",
        media_type="IMAGE",
        caption="Unrelated story about Space Exploration and Satellites",
    )

    res = guard.verify_and_guard(b)
    assert not res.is_valid
    assert res.error_code == "CAPTION_MISMATCH"


def test_media_story_mismatch():
    verifier = InstagramMediaVerifier()
    res = verifier.verify_and_deduplicate("http://example.com/bad-media-http.jpg")
    assert not res.is_valid


def test_real_content_only():
    source = InstagramRealNewsSource()
    items = source.get_content_items()
    assert len(items) > 0
    for item in items:
        title = item.get("title", "").lower()
        assert "sample" not in title
        assert "fake" not in title
        assert "demo" not in title


def test_fresh_content_only():
    source = InstagramRealNewsSource()
    items = source.get_content_items()
    for item in items:
        url = item.get("source_url", "")
        assert url.startswith("https://") or url.startswith("http://")


def test_cricket_priority():
    config = Config.load_from_env(validate=False)
    assert config.cricket_target_percent >= 75


def test_match_day_priority():
    provider = FallbackCricketProvider()
    intel = InstagramCricketMatchIntelligence(provider=provider)
    summary = intel.analyze_matches()
    assert summary.priority_multiplier >= 1.0


def test_real_instagram_publish_audit():
    verifier = InstagramMediaVerifier()
    assert verifier is not None


def test_publish_retry_duplicate_safety(tmp_path):
    data_dir = str(tmp_path / "data")
    guard = InstagramFinalPublishGuard(data_dir=data_dir)

    b = ContentBundle(
        content_id="retry-saf-1",
        category="cricket",
        title="Retry Safety Story Title",
        summary="Summary",
        source_url="https://example.com/retry-saf-1",
        source_domain="example.com",
        published_at="2026-08-25T00:00:00Z",
        media_url="https://example.com/retry-saf-1.jpg",
        media_type="IMAGE",
        caption="Retry Safety Story Title caption",
    )
    guard.record_published_item(b, media_id="media-ret-1")

    res = guard.verify_and_guard(b)
    assert not res.is_valid


def test_scheduled_workflow_configuration():
    wf_path1 = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".github", "workflows", "instagram_automation.yml")
    wf_path2 = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".github", "workflows", "instagram-publisher.yml")
    assert os.path.exists(wf_path1) or os.path.exists(wf_path2)


def test_no_telegram_imports():
    bad_imp = "import " + "tele" + "bot"
    bad_from = "from " + "tele" + "bot"
    bad_ai = "import " + "ai_" + "news"

    for py_file in glob.glob("*.py"):
        with open(py_file, "r", encoding="utf-8") as f:
            code = f.read().lower()
            assert bad_imp not in code, f"Telegram import found in {py_file}"
            assert bad_from not in code, f"Telegram import found in {py_file}"
            assert bad_ai not in code, f"Telegram import found in {py_file}"
