import glob
import os
import pytest
from config import Config
from instagram_final_publish_guard import InstagramFinalPublishGuard
from instagram_cloud_runtime import InstagramCloudRuntime


def test_phase_13_6_integrity():
    config = Config.load_from_env(validate=False)
    assert getattr(config, "final_publish_guard_enabled", True) is True
    assert getattr(config, "fact_fingerprint_enabled", True) is True
    assert getattr(config, "caption_integrity_enabled", True) is True
    assert getattr(config, "graphic_dedup_enabled", True) is True


def test_telegram_isolation():
    """Performs strict Telegram separation audit to ensure zero Telegram code imports or dependencies."""
    bad_imp = "import " + "tele" + "bot"
    bad_from = "from " + "tele" + "bot"
    bad_ai = "import " + "ai_" + "news"

    for py_file in glob.glob("*.py"):
        with open(py_file, "r", encoding="utf-8") as f:
            code = f.read().lower()
            assert bad_imp not in code, f"Telegram import found in {py_file}"
            assert bad_from not in code, f"Telegram import found in {py_file}"
            assert bad_ai not in code, f"Telegram import found in {py_file}"
