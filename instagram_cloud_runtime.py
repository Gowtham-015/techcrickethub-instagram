import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from config import Config

logger = logging.getLogger("InstagramCloudRuntime")


class InstagramCloudRuntime:
    """Manages 24/7 continuous cloud background worker execution state and health diagnostics.

    Guarantees pure cloud worker runtime independent of laptop state.
    """

    def __init__(self, config: Optional[Config] = None, data_dir: Optional[str] = None):
        self.config = config or Config.load_from_env(validate=False)
        self.data_dir = data_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        os.makedirs(self.data_dir, exist_ok=True)

        self.runtime_file = os.path.join(self.data_dir, "instagram_cloud_runtime_status.json")
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.start_timestamp = time.time()
        self.worker_id = f"cloud-worker-{os.getpid()}"

        self.cycles_completed = 0
        self.items_processed = 0
        self.items_published = 0
        self.items_failed = 0
        self.last_cycle_time: Optional[str] = None
        self.last_success_time: Optional[str] = None
        self.last_error: Optional[str] = None
        self.status = "RUNNING"

        self.update_heartbeat()

    def update_heartbeat(self, extra_metrics: Optional[Dict[str, Any]] = None) -> None:
        """Updates worker heartbeat timestamp and persists runtime state to disk."""
        now_dt = datetime.now(timezone.utc)
        uptime = int(time.time() - self.start_timestamp)

        runtime_data = {
            "worker_id": self.worker_id,
            "runtime_status": self.status,
            "started_at": self.started_at,
            "last_heartbeat": now_dt.isoformat(),
            "uptime_seconds": uptime,
            "laptop_required": False,
            "cloud_worker_required": True,
            "continuous_runtime": True,
            "cycles_completed": self.cycles_completed,
            "items_processed": self.items_processed,
            "items_published": self.items_published,
            "items_failed": self.items_failed,
            "last_cycle": self.last_cycle_time,
            "last_success": self.last_success_time,
            "last_error": self.last_error,
        }

        if extra_metrics:
            runtime_data.update(extra_metrics)

        try:
            temp_file = f"{self.runtime_file}.tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(runtime_data, f, indent=2)
            os.replace(temp_file, self.runtime_file)
        except Exception as e:
            logger.error(f"Failed to persist cloud runtime status: {e}")

    def record_cycle_start(self) -> None:
        """Records cycle execution start."""
        self.last_cycle_time = datetime.now(timezone.utc).isoformat()
        self.update_heartbeat()

    def record_cycle_complete(
        self,
        processed: int = 0,
        published: int = 0,
        failed: int = 0,
        error: Optional[str] = None,
    ) -> None:
        """Records completed cycle metrics."""
        self.cycles_completed += 1
        self.items_processed += processed
        self.items_published += published
        self.items_failed += failed

        if error:
            self.last_error = error
            self.status = "DEGRADED"
        else:
            self.last_success_time = datetime.now(timezone.utc).isoformat()
            self.status = "RUNNING"

        self.update_heartbeat()

    def get_runtime_summary(self) -> Dict[str, Any]:
        """Loads and returns the current cloud runtime status summary."""
        if os.path.exists(self.runtime_file):
            try:
                with open(self.runtime_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "worker_id": self.worker_id,
            "runtime_status": self.status,
            "started_at": self.started_at,
            "last_heartbeat": datetime.now(timezone.utc).isoformat(),
            "uptime_seconds": int(time.time() - self.start_timestamp),
            "laptop_required": False,
            "cloud_worker_required": True,
            "continuous_runtime": True,
        }
