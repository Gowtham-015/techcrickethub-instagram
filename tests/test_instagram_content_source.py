import json
import pytest
from exceptions import InstagramConfigError
from local_content_source import LocalContentSource


def test_local_content_source_loading(tmp_path):
    sample_data = [
        {
            "id": "item-1",
            "title": "Title",
            "summary": "Summary",
            "category": "cricket",
            "image_url": "https://example.com/image.jpg",
            "media_type": "IMAGE",
        }
    ]
    file_path = tmp_path / "sample.json"
    file_path.write_text(json.dumps(sample_data), encoding="utf-8")

    source = LocalContentSource(json_path=str(file_path))
    items = source.get_content_items()

    assert len(items) == 1
    assert items[0]["id"] == "item-1"


def test_local_content_source_missing_file():
    source = LocalContentSource(json_path="non_existent_file.json")
    with pytest.raises(InstagramConfigError) as exc_info:
        source.get_content_items()
    assert "Content file not found" in str(exc_info.value)


def test_local_content_source_invalid_json(tmp_path):
    file_path = tmp_path / "invalid.json"
    file_path.write_text("NOT_VALID_JSON{", encoding="utf-8")

    source = LocalContentSource(json_path=str(file_path))
    with pytest.raises(InstagramConfigError) as exc_info:
        source.get_content_items()
    assert "Failed to parse JSON content" in str(exc_info.value)


def test_local_content_source_non_list_payload(tmp_path):
    file_path = tmp_path / "dict.json"
    file_path.write_text(json.dumps({"key": "value"}), encoding="utf-8")

    source = LocalContentSource(json_path=str(file_path))
    with pytest.raises(InstagramConfigError) as exc_info:
        source.get_content_items()
    assert "Expected a JSON list of items" in str(exc_info.value)
