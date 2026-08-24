import os
import json
import pytest
from instagram_production_audit import InstagramProductionAuditStore


def test_production_audit_recording(tmp_path):
    audit_file = str(tmp_path / "audit.json")
    store = InstagramProductionAuditStore(audit_path=audit_file)

    rec = store.record_audit(
        content_id="test-001",
        media_type="IMAGE",
        category="cricket",
        status="PUBLISHED",
        creation_id="c-123",
        media_id="m-456",
        duration=1.23,
        dry_run=False,
        production_mode="PRODUCTION",
    )

    assert rec["content_id"] == "test-001"
    assert rec["status"] == "PUBLISHED"
    assert rec["creation_id"] == "c-123"
    assert rec["media_id"] == "m-456"

    loaded = store.load_records()
    assert len(loaded) == 1
    assert loaded[0]["content_id"] == "test-001"


def test_production_audit_secret_redaction(tmp_path):
    audit_file = str(tmp_path / "audit.json")
    store = InstagramProductionAuditStore(audit_path=audit_file)
    secret_err = "API failure with access_token=IGAAW7oCvAZBS1BZAFowdVRmMC1rOTZANS1VINkM2WUdTbjd2cHFXNUQxZAHBNOWp0UWZA5U3pvWXR6eThFNENzUmJuZA25LQ3YwZAWVSSnFDeHM0akhGbEVoQWdOZAzJWSUtjMkVtVlBMR3BBc1o2amJKTjJsS29Qb3NERGhqTGxGWGVOVQZDZD"

    store.record_audit(
        content_id="test-002",
        media_type="REEL",
        category="sports",
        status="FAILED",
        error_type=secret_err,
    )

    loaded = store.load_records()
    err_text = loaded[0]["error_type"]
    assert "IGAAW7oCv" not in err_text
    assert "[REDACTED]" in err_text


def test_production_audit_summary(tmp_path):
    audit_file = str(tmp_path / "audit.json")
    store = InstagramProductionAuditStore(audit_path=audit_file)

    store.record_audit("c-1", "IMAGE", "cricket", "PUBLISHED")
    store.record_audit("c-2", "REEL", "cricket", "FAILED")
    store.record_audit("c-3", "IMAGE", "technology", "BLOCKED")

    summary = store.get_summary()
    assert summary["total_audit_events"] == 3
    assert summary["published_count"] == 1
    assert summary["failed_count"] == 1
    assert summary["blocked_count"] == 1
