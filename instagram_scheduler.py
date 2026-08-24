import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import List, Optional

from config import Config
from exceptions import InstagramConfigError, InstagramError
from instagram_pipeline import InstagramContent, InstagramContentPipeline, PipelineResult
from instagram_queue import InstagramQueue, InstagramQueueItem
from security import RedactingFormatter, redact_token


class InstagramScheduler:
    """Standalone scheduler for Instagram content items with process locking, timezone handling,

    retry policies, and dry-run execution safety.
    """

    def __init__(
        self,
        queue: Optional[InstagramQueue] = None,
        pipeline: Optional[InstagramContentPipeline] = None,
        config: Optional[Config] = None,
        lock_path: Optional[str] = None,
    ):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.lock_path = lock_path or os.path.join(base_dir, "data", "instagram_scheduler.lock")

        self.config = config or Config.load_from_env(validate=False)
        self.queue = queue or InstagramQueue(max_queue_size=self.config.max_queue_size)
        self.pipeline = pipeline or InstagramContentPipeline(dry_run=self.config.dry_run)

        self.logger = logging.getLogger("InstagramScheduler")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = RedactingFormatter(
                fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                token=self.config.access_token,
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def acquire_lock(self, stale_timeout_seconds: int = 300) -> bool:
        """Acquires an Instagram-only process lock file with stale lock detection and auto-recovery."""
        os.makedirs(os.path.dirname(self.lock_path), exist_ok=True)

        if os.path.exists(self.lock_path):
            try:
                with open(self.lock_path, "r", encoding="utf-8") as f:
                    lock_data = json.load(f)
                lock_time = float(lock_data.get("timestamp", 0))

                if time.time() - lock_time > stale_timeout_seconds:
                    self.logger.warning(
                        f"Stale lock detected (age: {int(time.time() - lock_time)}s). Overriding lock."
                    )
                    self.release_lock()
                else:
                    self.logger.warning(
                        f"Active scheduler process lock found (PID: {lock_data.get('pid')}). Acquisition denied."
                    )
                    return False
            except Exception:
                self.release_lock()

        try:
            lock_payload = {
                "pid": os.getpid(),
                "timestamp": time.time(),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            with open(self.lock_path, "w", encoding="utf-8") as f:
                json.dump(lock_payload, f, indent=2)
            return True
        except Exception as e:
            self.logger.error(f"Failed to create scheduler lock file: {e}")
            return False

    def release_lock(self) -> None:
        """Safely removes the process lock file."""
        if os.path.exists(self.lock_path):
            try:
                os.remove(self.lock_path)
            except Exception as e:
                self.logger.error(f"Failed to remove scheduler lock file: {e}")

    @classmethod
    def parse_iso_datetime(cls, iso_str: str) -> datetime:
        """Parses ISO datetime string into a timezone-aware datetime object."""
        try:
            dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return datetime.now(timezone.utc)

    def is_due(self, item: InstagramQueueItem, now_dt: Optional[datetime] = None) -> bool:
        """Determines if a queue item is due for processing based on scheduled_at timestamp."""
        now = now_dt or datetime.now(timezone.utc)
        scheduled_dt = self.parse_iso_datetime(item.scheduled_at)
        return scheduled_dt <= now

    def process_due_items(self, limit: Optional[int] = None) -> List[PipelineResult]:
        """Loads due PENDING/SCHEDULED items from queue, executes processing through the pipeline,

        records progress, handles retries, and enforces dry-run safety.
        """
        if not self.acquire_lock():
            return []

        results: List[PipelineResult] = []
        try:
            items = self.queue.get_all_items()
            now = datetime.now(timezone.utc)

            due_items = [
                i for i in items if i.status in ("PENDING", "SCHEDULED") and self.is_due(i, now_dt=now)
            ]

            if limit and limit > 0:
                due_items = due_items[:limit]

            self.logger.info(f"Scheduler run started. Due items found: {len(due_items)}")

            for item in due_items:
                self.logger.info(f"Processing queue_id '{item.queue_id}' (content_id: {item.content_id})")

                # Mark PROCESSING
                self.queue.mark_processing(item.queue_id)

                # Convert to InstagramContent model
                content = InstagramContent(
                    title=item.title,
                    summary="",
                    category=item.category,
                    image_url=item.media_url if item.media_type == "IMAGE" else None,
                    video_url=item.media_url if item.media_type == "REEL" else None,
                    caption=item.caption,
                    media_type=item.media_type,
                    metadata={"content_id": item.content_id, "queue_id": item.queue_id},
                )

                # Execute through Phase 5 pipeline (respects INSTAGRAM_DRY_RUN)
                res = self.pipeline.process_content(content)
                results.append(res)

                if res.success:
                    if res.dry_run:
                        self.logger.info(f"Item '{item.queue_id}' processed in DRY_RUN mode. Marking SKIPPED.")
                        self.queue.update_status(item.queue_id, "SKIPPED", last_error=res.message)
                    else:
                        self.logger.info(f"Item '{item.queue_id}' published successfully. Media ID: {res.media_id}")
                        self.queue.mark_published(
                            item.queue_id,
                            media_id=res.media_id,
                            container_id=res.creation_id,
                        )
                else:
                    err_msg = redact_token(res.message or "Pipeline execution failed.")
                    self.logger.error(f"Item '{item.queue_id}' failed: {err_msg}")
                    self.queue.mark_failed(item.queue_id, error=err_msg)

            return results

        finally:
            self.release_lock()
