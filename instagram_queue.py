import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from exceptions import InstagramConfigError, InstagramError
from security import redact_token


VALID_STATUSES = {
    "PENDING",
    "SCHEDULED",
    "PROCESSING",
    "PUBLISHED",
    "FAILED",
    "CANCELLED",
    "DUPLICATE",
    "SKIPPED",
}


@dataclass
class InstagramQueueItem:
    """Represents a single queued content item for Instagram publishing."""

    queue_id: str
    content_id: Optional[str]
    media_type: str
    title: str
    media_url: str
    caption: str
    category: str
    scheduled_at: str
    status: str = "PENDING"
    created_at: str = ""
    attempt_count: int = 0
    last_error: Optional[str] = None
    published_media_id: Optional[str] = None
    created_media_container_id: Optional[str] = None

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if d.get("last_error"):
            d["last_error"] = redact_token(d["last_error"])
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InstagramQueueItem":
        return cls(
            queue_id=data.get("queue_id") or str(uuid.uuid4()),
            content_id=data.get("content_id"),
            media_type=str(data.get("media_type") or "IMAGE").upper(),
            title=data.get("title") or "",
            media_url=data.get("media_url") or "",
            caption=data.get("caption") or "",
            category=data.get("category") or "cricket",
            scheduled_at=data.get("scheduled_at") or datetime.now(timezone.utc).isoformat(),
            status=str(data.get("status") or "PENDING").upper(),
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
            attempt_count=int(data.get("attempt_count") or 0),
            last_error=redact_token(data.get("last_error")) if data.get("last_error") else None,
            published_media_id=data.get("published_media_id"),
            created_media_container_id=data.get("created_media_container_id"),
        )


class InstagramQueue:
    """Persistent queue manager for Instagram content items."""

    def __init__(self, queue_path: Optional[str] = None, max_queue_size: int = 50):
        if queue_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            queue_path = os.path.join(base_dir, "data", "instagram_queue.json")

        self.queue_path = queue_path
        self.max_queue_size = max_queue_size
        self._ensure_queue_file()

    def _ensure_queue_file(self) -> None:
        """Ensures directory and queue JSON file exist safely."""
        os.makedirs(os.path.dirname(self.queue_path), exist_ok=True)
        if not os.path.exists(self.queue_path):
            self._save_queue({"items": []})
        else:
            try:
                data = self._load_queue()
                if "items" not in data or not isinstance(data["items"], list):
                    self._save_queue({"items": []})
            except Exception:
                self._save_queue({"items": []})

    def _load_queue(self) -> Dict[str, Any]:
        """Loads raw JSON payload from file."""
        with open(self.queue_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_queue(self, data: Dict[str, Any]) -> None:
        """Atomic write to JSON queue file."""
        temp_path = f"{self.queue_path}.tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(temp_path, self.queue_path)

    def get_all_items(self) -> List[InstagramQueueItem]:
        """Returns all items in the queue as InstagramQueueItem objects."""
        data = self._load_queue()
        return [InstagramQueueItem.from_dict(item) for item in data.get("items", [])]

    def _save_items(self, items: List[InstagramQueueItem]) -> None:
        """Saves a list of InstagramQueueItem objects."""
        data = {"items": [item.to_dict() for item in items]}
        self._save_queue(data)

    def enqueue(self, item: InstagramQueueItem) -> InstagramQueueItem:
        """Enqueues a new item if not a duplicate and within queue capacity limits."""
        items = self.get_all_items()

        active_items = [i for i in items if i.status in ("PENDING", "SCHEDULED", "PROCESSING")]
        if len(active_items) >= self.max_queue_size:
            raise InstagramError(f"Queue capacity limit reached ({self.max_queue_size} items). Cannot enqueue.")

        for existing in items:
            if existing.status in ("PENDING", "SCHEDULED", "PROCESSING", "PUBLISHED"):
                if item.content_id and existing.content_id and existing.content_id == item.content_id:
                    raise InstagramError(f"Duplicate queue entry detected for content_id '{item.content_id}'.")
                if item.media_url and existing.media_url and existing.media_url == item.media_url and "maxresdefault.jpg" not in item.media_url:
                    raise InstagramError(f"Duplicate queue entry detected for media_url '{item.media_url}'.")

        items.append(item)
        self._save_items(items)
        return item

    def dequeue(self) -> Optional[InstagramQueueItem]:
        """Retrieves and returns the next due PENDING or SCHEDULED item."""
        items = self.get_all_items()
        for item in items:
            if item.status in ("PENDING", "SCHEDULED"):
                return item
        return None

    def get_pending(self) -> List[InstagramQueueItem]:
        """Returns all PENDING items."""
        return [i for i in self.get_all_items() if i.status == "PENDING"]

    def get_scheduled(self) -> List[InstagramQueueItem]:
        """Returns all SCHEDULED items."""
        return [i for i in self.get_all_items() if i.status == "SCHEDULED"]

    def update_status(
        self,
        queue_id: str,
        status: str,
        last_error: Optional[str] = None,
        published_media_id: Optional[str] = None,
        created_media_container_id: Optional[str] = None,
        increment_attempt: bool = False,
    ) -> Optional[InstagramQueueItem]:
        """Updates status and metadata for a queue item by queue_id."""
        status_clean = status.upper()
        if status_clean not in VALID_STATUSES:
            raise InstagramError(f"Invalid queue status: '{status}'. Must be one of {sorted(list(VALID_STATUSES))}.")

        items = self.get_all_items()
        target = None

        for item in items:
            if item.queue_id == queue_id:
                item.status = status_clean
                if last_error is not None:
                    item.last_error = redact_token(last_error)
                if published_media_id is not None:
                    item.published_media_id = published_media_id
                if created_media_container_id is not None:
                    item.created_media_container_id = created_media_container_id
                if increment_attempt:
                    item.attempt_count += 1
                target = item
                break

        if target:
            self._save_items(items)
        return target

    def mark_processing(self, queue_id: str) -> Optional[InstagramQueueItem]:
        return self.update_status(queue_id, "PROCESSING", increment_attempt=True)

    def mark_published(self, queue_id: str, media_id: Optional[str] = None, container_id: Optional[str] = None) -> Optional[InstagramQueueItem]:
        return self.update_status(queue_id, "PUBLISHED", published_media_id=media_id, created_media_container_id=container_id)

    def mark_failed(self, queue_id: str, error: str) -> Optional[InstagramQueueItem]:
        return self.update_status(queue_id, "FAILED", last_error=error)

    def mark_cancelled(self, queue_id: str) -> Optional[InstagramQueueItem]:
        return self.update_status(queue_id, "CANCELLED")

    def mark_duplicate(self, queue_id: str) -> Optional[InstagramQueueItem]:
        return self.update_status(queue_id, "DUPLICATE")

    def retry_failed(self, max_retries: int = 3) -> List[InstagramQueueItem]:
        """Resets FAILED items with attempt_count < max_retries back to PENDING for retry."""
        items = self.get_all_items()
        retried = []
        for item in items:
            if item.status == "FAILED" and item.attempt_count < max_retries:
                item.status = "PENDING"
                item.last_error = f"Retrying attempt {item.attempt_count + 1}/{max_retries}"
                retried.append(item)
        if retried:
            self._save_items(items)
        return retried

    def remove(self, queue_id: str) -> bool:
        """Removes an item from the queue by queue_id."""
        items = self.get_all_items()
        new_items = [i for i in items if i.queue_id != queue_id]
        if len(new_items) != len(items):
            self._save_items(new_items)
            return True
        return False

    def clear(self) -> None:
        """Clears all items in the queue."""
        self._save_items([])

    def get_status_summary(self) -> Dict[str, int]:
        """Returns summary count of items grouped by status."""
        items = self.get_all_items()
        summary = {s: 0 for s in sorted(list(VALID_STATUSES))}
        summary["total"] = len(items)
        for item in items:
            st = item.status.upper()
            if st in summary:
                summary[st] += 1
        return summary
