import os
import tempfile
from config import Config
from instagram_automation_engine import InstagramAutomationEngine
from instagram_health import InstagramHealthTracker


def test_production_config_defaults():
    cfg = Config.load_from_env(validate=False)
    assert isinstance(cfg.dry_run, bool)
    assert cfg.timezone == "Asia/Kolkata"


def test_production_health_summary():
    with tempfile.TemporaryDirectory() as tmpdir:
        health_path = os.path.join(tmpdir, "health.json")
        tracker = InstagramHealthTracker(health_path=health_path)
        tracker.set_status("RUNNING")

        summary = tracker.get_production_health_summary()
        assert summary["status"] == "RUNNING"
        assert summary["health_label"] == "HEALTHY"

        tracker.record_cycle(processed=1, published=0, failed=1, error="API timeout error")
        summary_err = tracker.get_production_health_summary()
        assert summary_err["health_label"] == "DEGRADED"


def test_production_lock_recovery():
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = os.path.join(tmpdir, "test.lock")
        engine = InstagramAutomationEngine(lock_path=lock_path)

        assert engine.acquire_lock() is True
        engine.release_lock()
        assert os.path.exists(lock_path) is False


def test_telegram_isolation_audit():
    # Audit Instagram code directory for accidental Telegram imports
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    py_files = [
        os.path.join(base_dir, f)
        for f in os.listdir(base_dir)
        if f.endswith(".py") and not f.startswith("test_")
    ]

    telegram_refs = []
    for filepath in py_files:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read().lower()
            if "import telegram" in content or "from telegram" in content or "ai_news" in content:
                telegram_refs.append(filepath)

    assert len(telegram_refs) == 0, f"Telegram references detected in: {telegram_refs}"
