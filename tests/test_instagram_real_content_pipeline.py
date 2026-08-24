import pytest
from config import Config
from instagram_caption_generator import InstagramCaptionGenerator
from instagram_pipeline import InstagramContent, InstagramContentPipeline
from instagram_real_news_source import InstagramRealNewsSource
from instagram_source_verifier import InstagramSourceVerifier


def test_real_content_pipeline_caption_attribution():
    gen = InstagramCaptionGenerator()
    caption = gen.generate_caption(
        title="Jaiswal Century in 1st Test",
        summary="Yashasvi Jaiswal scored an outstanding 100 vs Sri Lanka.",
        category="cricket",
        source="ESPNCricinfo",
    )

    assert "📌 Source: ESPNCricinfo" in caption
    assert "#Cricket" in caption
    assert "#TechCricketHub" in caption


def test_real_content_pipeline_dry_run_execution():
    cfg = Config.load_from_env(validate=False)
    cfg.dry_run = True

    pipeline = InstagramContentPipeline(dry_run=cfg.dry_run)
    content = InstagramContent(
        title="India vs Sri Lanka 1st Test",
        summary="India takes dominant lead in Colombo.",
        category="cricket",
        source="ESPNCricinfo",
        image_url="https://i.ytimg.com/vi/pbYX4gp_5kE/maxresdefault.jpg",
        media_type="IMAGE",
        metadata={"content_id": "real-test-123"},
    )
    res = pipeline.process_content(content)

    assert res.success is True
    assert res.dry_run is True
    assert res.status == "SKIPPED"
