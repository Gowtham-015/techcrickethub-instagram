import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from security import redact_token


class InstagramHealthTracker:
    """Manages persistent engine health, uptime metrics, and heartbeat state in data/instagram_health.json."""

    def __init__(self, health_path: Optional[str] = None):
        if health_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            health_path = os.path.join(base_dir, "data", "instagram_health.json")

        self.health_path = health_path
        self._start_timestamp: Optional[float] = None
        self._ensure_health_file()

    def _ensure_health_file(self) -> None:
        """Ensures directory and health JSON file exist safely."""
        os.makedirs(os.path.dirname(self.health_path), exist_ok=True)
        if not os.path.exists(self.health_path):
            self._save_health(self._default_state())
        else:
            try:
                data = self._load_health()
                if "status" not in data:
                    self._save_health(self._default_state())
            except Exception:
                self._save_health(self._default_state())

    @classmethod
    def _default_state(cls) -> Dict[str, Any]:
        """Returns default initial health state."""
        return {
            "status": "STOPPED",
            "started_at": None,
            "last_heartbeat": None,
            "last_cycle_at": None,
            "last_success_at": None,
            "last_error": None,
            "cycles_completed": 0,
            "items_processed": 0,
            "items_published": 0,
            "items_failed": 0,
            "uptime_seconds": 0,
            "analytics_events_recorded": 0,
            "optimization_runs": 0,
            "optimization_recommendations": 0,
        }

    def _load_health(self) -> Dict[str, Any]:
        """Loads health dictionary from file."""
        with open(self.health_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_health(self, data: Dict[str, Any]) -> None:
        """Atomic write to JSON health file."""
        temp_path = f"{self.health_path}.tmp"
        if data.get("last_error"):
            data["last_error"] = redact_token(data["last_error"])
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(temp_path, self.health_path)

    def set_status(self, status: str) -> None:
        """Updates overall engine status (RUNNING, STOPPED, STARTING, ERROR)."""
        data = self._load_health()
        data["status"] = status.upper()
        now_iso = datetime.now(timezone.utc).isoformat()
        if status.upper() == "RUNNING":
            if not data.get("started_at"):
                data["started_at"] = now_iso
            self._start_timestamp = time.time()
            data["last_heartbeat"] = now_iso
        elif status.upper() == "STOPPED":
            self._start_timestamp = None
        self._save_health(data)

    def update_heartbeat(self) -> None:
        """Updates last_heartbeat timestamp and uptime_seconds."""
        data = self._load_health()
        now_iso = datetime.now(timezone.utc).isoformat()
        data["last_heartbeat"] = now_iso

        if self._start_timestamp:
            data["uptime_seconds"] = int(time.time() - self._start_timestamp)

        self._save_health(data)

    def record_cycle(
        self,
        processed: int = 0,
        published: int = 0,
        failed: int = 0,
        error: Optional[str] = None,
    ) -> None:
        """Records metrics for a completed automation cycle."""
        data = self._load_health()
        now_iso = datetime.now(timezone.utc).isoformat()

        data["last_cycle_at"] = now_iso
        data["cycles_completed"] = int(data.get("cycles_completed") or 0) + 1
        data["items_processed"] = int(data.get("items_processed") or 0) + processed
        data["items_published"] = int(data.get("items_published") or 0) + published
        data["items_failed"] = int(data.get("items_failed") or 0) + failed

        if error:
            data["last_error"] = redact_token(error)
        else:
            data["last_success_at"] = now_iso

        if self._start_timestamp:
            data["uptime_seconds"] = int(time.time() - self._start_timestamp)

        self._save_health(data)

    def record_analytics_activity(self, events_added: int = 1, optimization_run: bool = False) -> None:
        """Records analytics activity counters."""
        data = self._load_health()
        data["analytics_events_recorded"] = int(data.get("analytics_events_recorded") or 0) + events_added
        if optimization_run:
            data["optimization_runs"] = int(data.get("optimization_runs") or 0) + 1
            data["optimization_recommendations"] = int(data.get("optimization_recommendations") or 0) + 1
        self._save_health(data)

    def get_health_summary(self) -> Dict[str, Any]:
        """Returns copy of current health status summary."""
        return self._load_health()

    def reset_test_state(self) -> None:
        """Resets health state file for clean testing."""
        self._save_health(self._default_state())
