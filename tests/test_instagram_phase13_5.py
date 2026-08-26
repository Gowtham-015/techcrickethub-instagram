import glob
import os
import pytest
from config import Config


def test_telegram_isolation_strict():
    """Rule 1 Audit: Asserts that zero Telegram modules/code/credentials exist in Python source files."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    py_files = glob.glob(os.path.join(base_dir, "*.py"))

    bad_imp = "import " + "tele" + "bot"
    bad_from = "from " + "tele" + "bot"
    bad_tg = "import " + "tele" + "gram_bot"
    bad_ai = "import " + "ai_" + "news"

    for py_file in py_files:
        with open(py_file, "r", encoding="utf-8") as f:
            code = f.read().lower()
            assert bad_imp not in code, f"Forbidden Telegram import found in {py_file}"
            assert bad_from not in code, f"Forbidden Telegram import found in {py_file}"
            assert bad_tg not in code, f"Forbidden Telegram import found in {py_file}"
            assert bad_ai not in code, f"Forbidden ai_news import found in {py_file}"


def test_config_target_ratios():
    config = Config.load_from_env(validate=False)
    assert config.reel_target_percent == 80
    assert config.image_target_percent == 20
    assert config.cricket_target_percent == 75
