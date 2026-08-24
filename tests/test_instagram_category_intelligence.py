from instagram_category_intelligence import InstagramCategoryIntelligence


def test_detect_category_cricket():
    intel = InstagramCategoryIntelligence()
    cat, conf = intel.detect_category(
        title="Rohit Sharma Scores Century in IPL Match",
        summary="India team captain hits 100 runs in T20 tournament.",
    )

    assert cat == "cricket"
    assert conf >= 0.5


def test_detect_category_ai():
    intel = InstagramCategoryIntelligence()
    cat, conf = intel.detect_category(
        title="OpenAI Releases New Neural Network LLM Model",
        summary="Generative AI ChatGPT updates performance benchmarks.",
    )

    assert cat == "ai"
    assert conf >= 0.5


def test_detect_category_unknown_fallback():
    intel = InstagramCategoryIntelligence()
    cat, conf = intel.detect_category(
        title="Random Text With No Keywords",
        summary="Generic description",
        default_category="sports",
    )

    assert cat == "sports"
    assert conf == 0.0
