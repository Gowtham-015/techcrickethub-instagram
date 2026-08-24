import pytest
from unittest.mock import MagicMock
from config import Config
from instagram_client import InstagramAPIClient
from instagram_live_test import InstagramLiveTestRunner
from instagram_health import InstagramHealthTracker
from instagram_production_audit import InstagramProductionAuditStore


def test_live_test_single_post_execution(tmp_path):
    health_file = str(tmp_path / "health.json")
    audit_file = str(tmp_path / "audit.json")

    tracker = InstagramHealthTracker(health_path=health_file)
    audit = InstagramProductionAuditStore(audit_path=audit_file)

    cfg = Config.load_from_env(validate=False)
    cfg.dry_run = True
    cfg.max_live_test_posts = 1

    client = MagicMock(spec=InstagramAPIClient)

    runner = InstagramLiveTestRunner(
        config=cfg,
        client=client,
        health_tracker=tracker,
        audit_store=audit,
    )

    res = runner.run_live_test()
    assert res.success is True
    assert res.dry_run is True
    assert res.audit_recorded is True

    health_summary = tracker.get_health_summary()
    assert health_summary.get("live_test_count") == 1

    audit_summary = audit.get_summary()
    assert audit_summary["total_audit_events"] == 1


def test_live_test_limit_enforced(tmp_path):
    health_file = str(tmp_path / "health.json")
    audit_file = str(tmp_path / "audit.json")

    tracker = InstagramHealthTracker(health_path=health_file)
    audit = InstagramProductionAuditStore(audit_path=audit_file)

    cfg = Config.load_from_env(validate=False)
    cfg.dry_run = True
    cfg.max_live_test_posts = 1

    client = MagicMock(spec=InstagramAPIClient)

    runner = InstagramLiveTestRunner(
        config=cfg,
        client=client,
        health_tracker=tracker,
        audit_store=audit,
    )

    # First run succeeds
    res1 = runner.run_live_test()
    assert res1.success is True

    # Second run blocked by limit
    res2 = runner.run_live_test()
    assert res2.success is False
    assert "LIVE TEST LIMIT REACHED" in res2.message
