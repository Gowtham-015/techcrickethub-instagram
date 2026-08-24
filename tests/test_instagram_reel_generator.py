import os
import pytest
from instagram_reel_generator import InstagramReelGenerator, PIL_AVAILABLE


def test_reel_generator_frame_rendering():
    if not PIL_AVAILABLE:
        pytest.skip("Pillow is not installed")
    gen = InstagramReelGenerator()
    frame = gen.render_frame(
        title="India vs Sri Lanka Test Match",
        subtitle="Match Update",
        fact_text="Jaiswal scores century in 1st Test.",
        source="ESPNCricinfo",
    )

    assert frame.size == (1080, 1920)


def test_reel_generator_from_facts(tmp_path):
    gen = InstagramReelGenerator(output_dir=str(tmp_path))
    item = {
        "content_id": "test-reel-001",
        "title": "Jaiswal 100",
        "summary": "Yashasvi Jaiswal scored an outstanding century.",
        "source_name": "ESPNCricinfo",
    }
    res = gen.generate_reel_from_facts(item)

    assert isinstance(res, dict)
    assert res["success"] in (True, False)
    assert "action" in res
