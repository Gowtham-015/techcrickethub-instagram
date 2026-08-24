import pytest
from config import Config
from instagram_production_gate import InstagramProductionGate
from instagram_health import InstagramHealthTracker


def test_gate_dry_run_blocks_publishing():
    cfg = Config.load_from_env(validate=False)
    cfg.dry_run = True
    cfg.production_enabled = True
    gate = InstagramProductionGate(config=cfg)
    res = gate.evaluate()

    assert res.can_publish is False
    assert res.status == "DRY_RUN"
    assert "INSTAGRAM_DRY_RUN is enabled" in res.reasons[0]


def test_gate_production_disabled_blocks_publishing():
    cfg = Config.load_from_env(validate=False)
    cfg.dry_run = False
    cfg.production_enabled = False
    gate = InstagramProductionGate(config=cfg)
    res = gate.evaluate()

    assert res.can_publish is False
    assert res.status == "BLOCKED"
    assert "INSTAGRAM_PRODUCTION_ENABLED is set to false" in res.reasons[0]


def test_gate_missing_credentials_blocks_publishing():
    cfg = Config.load_from_env(validate=False)
    cfg.user_id = ""
    cfg.access_token = ""
    gate = InstagramProductionGate(config=cfg)
    res = gate.evaluate()

    assert res.can_publish is False
    assert res.status == "NOT_CONFIGURED"


def test_gate_valid_configuration_allows_publishing():
    cfg = Config.load_from_env(validate=False)
    cfg.user_id = "123456789"
    cfg.access_token = "valid_access_token_mock_123"
    cfg.dry_run = False
    cfg.production_enabled = True
    gate = InstagramProductionGate(config=cfg)
    res = gate.evaluate()

    assert res.can_publish is True
    assert res.status == "READY"


def test_gate_live_test_mode_allowed():
    cfg = Config.load_from_env(validate=False)
    cfg.user_id = "123456789"
    cfg.access_token = "valid_access_token_mock_123"
    cfg.dry_run = False
    cfg.live_test_enabled = True
    gate = InstagramProductionGate(config=cfg)
    res = gate.evaluate(is_live_test=True)

    assert res.can_publish is True
    assert res.status == "LIVE_TEST"


def test_gate_paused_status_blocks_publishing(tmp_path):
    health_file = str(tmp_path / "health.json")
    tracker = InstagramHealthTracker(health_path=health_file)
    tracker.record_publish_failure("API error 1", max_consecutive_failures=1)

    cfg = Config.load_from_env(validate=False)
    cfg.dry_run = False
    cfg.production_enabled = True

    gate = InstagramProductionGate(config=cfg, health_tracker=tracker)
    res = gate.evaluate()

    assert res.can_publish is False
    assert res.status == "BLOCKED"
    assert res.paused is True
