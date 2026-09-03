import json
import os
from instagram_optimizer import InstagramOptimizer


def test_growth_optimizer_insufficient_data(tmp_path):
    opt = InstagramOptimizer()
    res = opt.get_growth_recommendations(history_dir=str(tmp_path))
    assert res["confidence_status"] == "INSUFFICIENT_DATA"


def test_growth_optimizer_sufficient_data(tmp_path):
    eng_file = os.path.join(tmp_path, "instagram_engagement_history.json")
    mock_db = {}
    for i in range(12):
        mock_db[f"m_{i}"] = {
            "media_id": f"m_{i}",
            "status": "SUCCESS",
            "reach": 1500 if i % 2 == 0 else 500,
            "category": "launches" if i % 2 == 0 else "cricket",
        }
    with open(eng_file, "w", encoding="utf-8") as f:
        json.dump(mock_db, f)

    opt = InstagramOptimizer()
    opt.min_sample_size = 10
    res = opt.get_growth_recommendations(history_dir=str(tmp_path))

    assert res["confidence_status"] == "SUFFICIENT"
    assert res["top_category"] == "launches"
    assert res["category_weights"]["launches"] == 1.15
