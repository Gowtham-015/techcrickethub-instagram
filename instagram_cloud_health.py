import json
import logging
import os
import socket
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from config import Config
from instagram_cloud_storage import get_storage_provider

logger = logging.getLogger("InstagramCloudHealth")


class InstagramCloudHealth:
    """Manages cloud worker heartbeat, status tracking, watchdog health checks, and metrics persistence."""

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config.load_from_env(validate=False)
        self.storage = get_storage_provider()
        self.health_file = "instagram_cloud_health.json"

        self.worker_id = f"{socket.gethostname()}-{os.getpid()}"
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.worker_status = "STARTING"

        self.published_count = 0
        self.failed_count = 0
        self.duplicate_count = 0
        self.last_cycle_at: Optional[str] = None
        self.last_publish_attempt_at: Optional[str] = None
        self.last_publish_success_at: Optional[str] = None
        self.last_publish_failure_at: Optional[str] = None
        self.last_error: Optional[str] = None

        self.update_heartbeat(status="RUNNING")

    def update_heartbeat(
        self,
        status: Optional[str] = None,
        queue_size: int = 0,
        next_cycle_seconds: int = 60,
    ) -> Dict[str, Any]:
        """Updates and persists continuous cloud worker heartbeat."""
        if status:
            self.worker_status = status

        now_dt = datetime.now(timezone.utc)
        start_dt = datetime.fromisoformat(self.started_at)
        uptime = int((now_dt - start_dt).total_seconds())

        health_data = {
            "worker_id": self.worker_id,
            "worker_status": self.worker_status,
            "started_at": self.started_at,
            "last_heartbeat": now_dt.isoformat(),
            "uptime_seconds": uptime,
            "last_cycle": self.last_cycle_at or "N/A",
            "last_publish_attempt": self.last_publish_attempt_at or "N/A",
            "last_publish_success": self.last_publish_success_at or "N/A",
            "last_publish_failure": self.last_publish_failure_at or "N/A",
            "last_error": self.last_error or "None",
            "next_cycle": f"in {next_cycle_seconds}s",
            "queue_size": queue_size,
            "published_count": self.published_count,
            "failed_count": self.failed_count,
            "duplicate_count": self.duplicate_count,
        }

        self.storage.write_json(self.health_file, health_data)
        return health_data

    def record_cycle(self, discovered: int = 0, valid: int = 0, duplicates: int = 0, queued: int = 0) -> None:
        """Records cycle metrics."""
        self.last_cycle_at = datetime.now(timezone.utc).isoformat()
        self.duplicate_count += duplicates
        self.update_heartbeat(status="RUNNING")

    def record_publish_attempt(self) -> None:
        """Records publish attempt."""
        self.last_publish_attempt_at = datetime.now(timezone.utc).isoformat()
        self.update_heartbeat(status="PUBLISHING")

    def record_publish_success(self, media_id: str) -> None:
        """Records publish success."""
        self.published_count += 1
        self.last_publish_success_at = datetime.now(timezone.utc).isoformat()
        self.update_heartbeat(status="RUNNING")

    def record_publish_failure(self, error: str) -> None:
        """Records publish failure."""
        self.failed_count += 1
        self.last_publish_failure_at = datetime.now(timezone.utc).isoformat()
        self.last_error = error
        self.update_heartbeat(status="DEGRADED")

    def get_health_summary(self) -> Dict[str, Any]:
        """Returns health summary dict from storage or memory."""
        data = self.storage.read_json(self.health_file)
        if not data:
            return self.update_heartbeat()

        # Watchdog check for stale heartbeat (> threshold)
        last_hb_str = data.get("last_heartbeat")
        if last_hb_str:
            try:
                hb_dt = datetime.fromisoformat(last_hb_str)
                age = (datetime.now(timezone.utc) - hb_dt).total_seconds()
                if age > self.config.heartbeat_timeout_seconds:
                    data["worker_status"] = "DEGRADED"
                    data["health_note"] = f"Heartbeat stale ({int(age)}s > {self.config.heartbeat_timeout_seconds}s threshold)"
            except Exception:
                pass

        return data
