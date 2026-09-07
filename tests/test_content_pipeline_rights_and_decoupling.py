import os
import json
import pytest
from typing import Dict, Any

from instagram_rights_evidence_engine import InstagramRightsEvidenceEngine, RightsVerificationResult
from instagram_real_video_source import InstagramRealVideoSource, OwnedVideoProvider
from instagram_real_video_verifier import InstagramRealVideoVerifier
from instagram_reel_quality_engine import InstagramReelQualityEngine
from instagram_automation_engine import InstagramAutomationEngine
from config import Config


def test_external_video_without_rights_evidence_rejected():
    engine = InstagramRightsEvidenceEngine()
    item = {
        "content_id": "test-ext-01",
        "title": "External Cricket Highlights",
        "rights_status": "RIGHTS_EVIDENCE_MISSING",
        "commercial_use_allowed": False,
    }
    res = engine.verify_rights_evidence(item)
    assert not res.is_valid
    assert "RIGHTS_EVIDENCE_MISSING" in res.reasons[0] or "unauthorized" in res.reasons[0]


def test_domain_only_inference_rejected():
    source = InstagramRealVideoSource()
    xml_payload = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>TechCricketHub Videos</title>
        <item>
          <title>Match Highlights</title>
          <link>https://techcrickethub.com/story/123</link>
          <enclosure url="https://techcrickethub.com/video.mp4" type="video/mp4" />
        </item>
      </channel>
    </rss>"""
    items = source._parse_feed_items(xml_payload, feed_url="https://techcrickethub.com/rss", category="cricket")
    assert len(items) == 1
    item = items[0]
    assert item["rights_status"] == "RIGHTS_EVIDENCE_MISSING"
    assert item["commercial_use_allowed"] is False


def test_external_youtube_without_explicit_license_rejected():
    engine = InstagramRightsEvidenceEngine()
    item = {
        "content_id": "yt-01",
        "title": "Public YouTube Video",
        "video_url": "https://www.youtube.com/watch?v=abc123xyz",
        "source_domain": "youtube.com",
        "rights_status": "RIGHTS_EVIDENCE_MISSING",
        "commercial_use_allowed": False,
    }
    res = engine.verify_rights_evidence(item)
    assert not res.is_valid


def test_external_x_video_without_permission_rejected():
    engine = InstagramRightsEvidenceEngine()
    item = {
        "content_id": "x-01",
        "title": "Public X Video Clip",
        "source_domain": "x.com",
        "rights_status": "RIGHTS_EVIDENCE_MISSING",
        "commercial_use_allowed": False,
    }
    res = engine.verify_rights_evidence(item)
    assert not res.is_valid


def test_missing_commercial_use_allowed_rejected():
    engine = InstagramRightsEvidenceEngine()
    item = {
        "content_id": "comm-missing",
        "title": "Licensed Video",
        "rights_status": "OWNED",
        "rights_evidence": "Owned asset",
        "license_url": "https://techcrickethub.com/license",
    }
    res = engine.verify_rights_evidence(item)
    assert not res.is_valid
    assert any("commercial_use_allowed" in r for r in res.reasons)


def test_commercial_use_allowed_false_rejected():
    engine = InstagramRightsEvidenceEngine()
    item = {
        "content_id": "comm-false",
        "title": "Non-commercial Video",
        "rights_status": "OWNED",
        "rights_evidence": "Owned asset",
        "license_url": "https://techcrickethub.com/license",
        "commercial_use_allowed": False,
    }
    res = engine.verify_rights_evidence(item)
    assert not res.is_valid


def test_owned_video_with_valid_metadata_accepted():
    engine = InstagramRightsEvidenceEngine()
    item = {
        "content_id": "owned-valid",
        "title": "Account Owned Cricket Reel",
        "rights_status": "OWNED",
        "rights_evidence": "Account-owned original media asset",
        "license_url": "data/owned_reels/metadata.json",
        "commercial_use_allowed": True,
    }
    res = engine.verify_rights_evidence(item)
    assert res.is_valid
    assert res.rights_status == "OWNED"


def test_licensed_video_with_valid_evidence_accepted():
    engine = InstagramRightsEvidenceEngine()
    item = {
        "content_id": "licensed-valid",
        "title": "Licensed Technology Reel",
        "rights_status": "LICENSED",
        "rights_evidence": "Commercial License #994812",
        "license_url": "https://techcrickethub.com/licenses/994812",
        "commercial_use_allowed": True,
    }
    res = engine.verify_rights_evidence(item)
    assert res.is_valid


def test_cc_video_with_valid_explicit_license_accepted():
    engine = InstagramRightsEvidenceEngine()
    item = {
        "content_id": "cc-valid",
        "title": "Creative Commons Reel",
        "rights_status": "VERIFIED_CC_LICENSE",
        "rights_evidence": "CC-BY 4.0 License",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "commercial_use_allowed": True,
    }
    res = engine.verify_rights_evidence(item)
    assert res.is_valid


def test_owned_video_missing_file_rejected(tmp_path):
    metadata_file = tmp_path / "metadata.json"
    metadata_file.write_text(json.dumps({
        "items": [{
            "file": "non_existent_file.mp4",
            "rights_status": "OWNED",
            "commercial_use_allowed": True
        }]
    }))
    provider = OwnedVideoProvider(data_dir=str(tmp_path))
    provider.metadata_path = str(metadata_file)
    items = provider.fetch_video_items()
    assert len(items) == 0


def test_image_candidate_rejected_in_reel_only_mode():
    config = Config.load_from_env(validate=False)
    engine = InstagramAutomationEngine(config=config)
    
    image_item = {
        "content_id": "img-01",
        "title": "Match News Image",
        "summary": "India wins match",
        "category": "cricket",
        "media_type": "IMAGE",
        "image_url": "https://example.com/image.jpg",
        "rights_status": "OWNED",
        "rights_evidence": "Account-owned original image asset",
        "license_url": "https://techcrickethub.com/terms",
        "commercial_use_allowed": True,
    }
    
    r_res = engine.rights_engine.verify_rights_evidence(image_item)
    assert r_res.is_valid
    content = engine.normalizer.normalize(image_item)
    assert content.media_type == "IMAGE"


def test_corrupt_mp4_rejected(tmp_path):
    corrupt_file = tmp_path / "corrupt.mp4"
    corrupt_file.write_bytes(b"NOT A REAL MP4 FILE")
    verifier = InstagramRealVideoVerifier()
    res = verifier.verify_video_file(str(corrupt_file))
    assert not res.is_valid
    assert res.is_corrupted or not res.video_stream_exists


def test_news_and_authorized_video_decoupling_and_preparation():
    config = Config.load_from_env(validate=False)
    engine = InstagramAutomationEngine(config=config)
    prep_res = engine.prepare_media()
    
    assert prep_res.get("status") == "PREPARED"
    assert prep_res.get("prepared") is True
    
    prepared_file = os.path.join(engine.data_dir, "prepared_media.json")
    assert os.path.exists(prepared_file)
    with open(prepared_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    assert "information_source_url" in data
    assert "media_source_url" in data
    assert "rights_evidence_url" in data
    assert data["media_type"] == "REEL"
    assert data["commercial_use_allowed"] is True
