import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class InstagramMediaDeduplicator:
    """Manages processed media state in data/media_history.json to detect and prevent duplicate processing."""

    def __init__(self, history_path: Optional[str] = None):
        if history_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            history_path = os.path.join(base_dir, "data", "media_history.json")

        self.history_path = history_path
        self._ensure_history_file()

    def _ensure_history_file(self) -> None:
        """Ensures the directory and valid JSON structure exist."""
        os.makedirs(os.path.dirname(self.history_path), exist_ok=True)
        if not os.path.exists(self.history_path):
            self._save_history({"processed": []})
        else:
            try:
                data = self._load_history()
                if "processed" not in data or not isinstance(data["processed"], list):
                    self._save_history({"processed": []})
            except Exception:
                # Reset corrupted file safely
                self._save_history({"processed": []})

    def _load_history(self) -> Dict[str, Any]:
        """Loads state dictionary from JSON file."""
        with open(self.history_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_history(self, data: Dict[str, Any]) -> None:
        """Saves state dictionary to JSON file."""
        with open(self.history_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def compute_hash(cls, text: str) -> str:
        """Computes a SHA-256 hash for a given text string."""
        if not text:
            return ""
        return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()

    def is_duplicate(self, content_id: Optional[str] = None, url: Optional[str] = None) -> bool:
        """Checks if content_id or URL hash has already been processed."""
        if not content_id and not url:
            return False

        data = self._load_history()
        url_hash = self.compute_hash(url or "")

        for entry in data.get("processed", []):
            entry_id = entry.get("content_id")
            entry_hash = entry.get("media_hash")

            if content_id and entry_id and entry_id == content_id:
                return True
            if url_hash and entry_hash and entry_hash == url_hash and "maxresdefault.jpg" not in (url or ""):
                return True

        return False

    def mark_processed(
        self,
        content_id: Optional[str] = None,
        url: Optional[str] = None,
        status: str = "PROCESSED",
    ) -> None:
        """Records content item as processed in local state history."""
        if not content_id and not url:
            return

        data = self._load_history()
        url_hash = self.compute_hash(url or "")

        new_entry = {
            "content_id": content_id or "",
            "media_hash": url_hash,
            "url": url or "",
            "status": status,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }

        data.setdefault("processed", []).append(new_entry)
        self._save_history(data)
