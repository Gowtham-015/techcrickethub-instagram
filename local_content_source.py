import json
import os
from typing import Any, Dict, List, Optional
from exceptions import InstagramConfigError
from instagram_content_source import InstagramContentSource


class LocalContentSource(InstagramContentSource):
    """Local JSON-file content source implementation."""

    def __init__(self, json_path: Optional[str] = None):
        if json_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            json_path = os.path.join(base_dir, "data", "sample_content.json")

        self.json_path = json_path

    def get_content_items(self) -> List[Dict[str, Any]]:
        """Reads content items from the local JSON file."""
        if not os.path.exists(self.json_path):
            raise InstagramConfigError(f"Content file not found at path: '{self.json_path}'")

        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, list):
                raise InstagramConfigError(f"Expected a JSON list of items in '{self.json_path}', got {type(data).__name__}.")

            return data

        except json.JSONDecodeError as e:
            raise InstagramConfigError(f"Failed to parse JSON content from '{self.json_path}': {e}")
        except Exception as e:
            raise InstagramConfigError(f"Error reading local content source '{self.json_path}': {e}")
