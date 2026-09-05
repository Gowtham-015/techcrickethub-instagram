import os
import json
import tempfile
import pytest
from unittest.mock import patch, MagicMock

from config import Config
from instagram_content_bundle import ContentBundle
from instagram_final_publish_guard import InstagramFinalPublishGuard
from instagram_real_video_source import InstagramRealVideoSource
from instagram_public_media_host import PublicMediaHost
from instagram_automation_engine import InstagramAutomationEngine
from instagram_cricket_balancer import InstagramCricketBalancer


def test_critical_workflow_error_masking_removed():
    """Verify .github/workflows/instagram-publisher.yml has zero || true suppressions in production steps."""
    wf_path = os.path.join(os.path.dirname(__file__), "..", ".github", "workflows", "instagram-publisher.yml")
    with open(wf_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "git add -A || true" not in content
    assert "git reset --hard HEAD || true" not in content
    assert "git pull origin main --rebase || true" not in content
    assert "2>/dev/null || true" not in content
    assert "python main.py --cloud-status || true" not in content


def test_prepare_failure_prevents_publish(tmp_path):
    """Verify Phase B publish_prepared fails closed if prepared_media.json is missing."""
    config = Config.load_from_env(validate=False)
    data_dir = str(tmp_path / "data")
    engine = InstagramAutomationEngine(config=config, data_dir=data_dir)

    res = engine.publish_prepared()
    assert res["status"] == "FAILED"
    assert "Could not prepare media" in res["reason"] or "prepared_media.json" in res["reason"]


def test_github_raw_404_prevents_meta_publishing():
    """Verify PublicMediaHost.verify_public_url returns invalid on HTTP 404 / inaccessible URL when strict_production=True."""
    host = PublicMediaHost()
    res = host.verify_public_url("https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/non_existent_video_asset_9999.mp4", strict_production=True, retries=1, delay_sec=0.1)
    assert res["is_valid"] is False
    assert res["error_code"] == "PUBLIC_MEDIA_NOT_ACCESSIBLE"


def test_domain_name_cannot_infer_rights():
    """Verify domain names containing bcci, official, icc do NOT grant rights if explicit evidence tags are missing."""
    source = InstagramRealVideoSource()
    xml_content = """<rss version="2.0">
      <channel>
        <item>
          <title>Official BCCI Match Highlights</title>
          <link>https://www.bcci.tv/video/1001/highlights</link>
          <description>Match highlights from official BCCI channel</description>
          <enclosure url="https://video.bcci.tv/stream.mp4" type="video/mp4"/>
        </item>
      </channel>
    </rss>"""

    items = source._parse_feed_items(xml_content, feed_url="https://www.bcci.tv/rss", category="cricket")
    assert len(items) == 1
    assert items[0]["media_rights_status"] == "RIGHTS_EVIDENCE_MISSING"

    candidates = source.discover_video_items(category="cricket", limit=5)
    for c in candidates:
        assert c["media_rights_status"] != "RIGHTS_EVIDENCE_MISSING"
        assert c["media_rights_status"] in source.ALLOWED_RIGHTS_STATUSES


def test_authorized_without_evidence_rejected():
    """Verify rights_status = AUTHORIZED with empty evidence URL / type is REJECTED by InstagramFinalPublishGuard."""
    guard = InstagramFinalPublishGuard()
    bundle = ContentBundle(
        content_id="test-auth-no-ev",
        category="cricket",
        title="Test Authorized Without Evidence",
        summary="Summary test",
        source_url="https://example.com/story-auth",
        source_domain="example.com",
        published_at="2026-08-25T00:00:00Z",
        media_url="https://example.com/video.mp4",
        media_type="REEL",
        media_rights_status="AUTHORIZED",
        caption="Test Authorized Without Evidence #Cricket",
    )
    bundle.rights_evidence_type = "NONE"
    bundle.rights_evidence_url = ""

    res = guard.verify_and_guard(bundle)
    assert res.is_valid is False
    assert res.error_code == "RIGHTS_EVIDENCE_MISSING"


def test_cc_license_allowed_without_evidence_rejected():
    """Verify rights_status = CC_LICENSE_ALLOWED with empty rights_evidence_url is REJECTED."""
    guard = InstagramFinalPublishGuard()
    bundle = ContentBundle(
        content_id="test-cc-no-url",
        category="cricket",
        title="Test CC Allowed Without Evidence URL",
        summary="Summary test",
        source_url="https://example.com/story-cc",
        source_domain="example.com",
        published_at="2026-08-25T00:00:00Z",
        media_url="https://example.com/video.mp4",
        media_type="REEL",
        media_rights_status="CC_LICENSE_ALLOWED",
        caption="Test CC Allowed #Cricket",
    )
    bundle.rights_evidence_type = "CREATIVE_COMMONS"
    bundle.rights_evidence_url = ""

    res = guard.verify_and_guard(bundle)
    assert res.is_valid is False
    assert res.error_code == "RIGHTS_EVIDENCE_MISSING"


def test_missing_rights_rejected():
    """Verify RIGHTS_EVIDENCE_MISSING is REJECTED by publish guard."""
    guard = InstagramFinalPublishGuard()
    bundle = ContentBundle(
        content_id="test-missing-rights",
        category="cricket",
        title="Test Missing Rights Rejection",
        summary="Summary test",
        source_url="https://example.com/story-missing",
        source_domain="example.com",
        published_at="2026-08-25T00:00:00Z",
        media_url="https://example.com/video.mp4",
        media_type="REEL",
        media_rights_status="RIGHTS_EVIDENCE_MISSING",
        caption="Test Missing Rights #Cricket",
    )

    res = guard.verify_and_guard(bundle)
    assert res.is_valid is False
    assert res.error_code == "RIGHTS_EVIDENCE_MISSING"


def test_oceans_and_sample_videos_rejected():
    """Verify oceans.mp4 and sample videos are REJECTED in production publish guard."""
    guard = InstagramFinalPublishGuard()
    bundle = ContentBundle(
        content_id="test-oceans-mp4",
        category="cricket",
        title="Oceans Test Video",
        summary="Oceans summary",
        source_url="https://example.com/oceans",
        source_domain="example.com",
        published_at="2026-08-25T00:00:00Z",
        media_url="https://vjs.zencdn.net/v/oceans.mp4",
        media_type="REEL",
        media_rights_status="LICENSED",
        caption="Oceans Test Video #Cricket",
    )

    res = guard.verify_and_guard(bundle)
    assert res.is_valid is False
    assert res.error_code in ("INVALID_MEDIA", "DUPLICATE_MEDIA_URL", "DISALLOWED_DOMAIN")


def test_single_item_cycles_maintain_persistent_balancing(tmp_path):
    """Verify max_items_per_cycle = 1 evaluates persistent published history and selects Tech when in deficit."""
    config = Config.load_from_env(validate=False)
    config.max_items_per_cycle = 1
    data_dir = str(tmp_path / "data")

    engine = InstagramAutomationEngine(config=config, data_dir=data_dir)

    # Seed history with 25 Cricket items and 2 Tech items
    history = []
    for i in range(25):
        history.append({"content_id": f"c-{i}", "category": "cricket", "media_type": "REEL"})
    for i in range(2):
        history.append({"content_id": f"t-{i}", "category": "technology", "media_type": "REEL"})

    with open(os.path.join(data_dir, "instagram_published_history.json"), "w", encoding="utf-8") as f:
        json.dump({"items": history}, f)

    b_eval = engine.cricket_balancer.evaluate_balance(engine.final_publish_guard.get_published_history())
    assert b_eval.should_prefer_tech is True
    assert b_eval.non_cricket_count == 2


def test_successful_reel_publication_records_real_media_id(tmp_path):
    """Verify recording published item persists media ID, permalink, SHA256, and metadata correctly."""
    data_dir = str(tmp_path / "data")
    guard = InstagramFinalPublishGuard(data_dir=data_dir)

    bundle = ContentBundle(
        content_id="pub-rec-001",
        category="cricket",
        title="Published Reel Record Test",
        summary="Summary test",
        source_url="https://example.com/story-rec-001",
        source_domain="example.com",
        published_at="2026-08-25T00:00:00Z",
        media_url="https://example.com/real_reel.mp4",
        media_type="REEL",
        media_rights_status="LICENSED",
        caption="Published Reel Record Test #Cricket",
    )

    guard.record_published_item(bundle=bundle, media_id="18991234567890123", permalink="https://www.instagram.com/reel/C_test123/")

    hist = guard.get_published_history()
    assert len(hist) == 1
    assert hist[0]["instagram_media_id"] == "18991234567890123"
    assert hist[0]["instagram_permalink"] == "https://www.instagram.com/reel/C_test123/"
    assert hist[0]["content_id"] == "pub-rec-001"
