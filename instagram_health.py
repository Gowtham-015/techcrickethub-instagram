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
            "production_enabled": False,
            "production_gate_status": "DRY_RUN",
            "api_connected": False,
            "last_live_test_at": None,
            "last_published_at": None,
            "last_publish_error": None,
            "consecutive_publish_failures": 0,
            "production_paused": False,
            "pause_reason": None,
            "live_test_count": 0,
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
        if data.get("last_publish_error"):
            data["last_publish_error"] = redact_token(data["last_publish_error"])
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

    def record_publish_success(self, media_id: str, is_live_test: bool = False) -> None:
        """Records successful publishing attempt and resets consecutive failures."""
        data = self._load_health()
        now_iso = datetime.now(timezone.utc).isoformat()
        data["last_published_at"] = now_iso
        data["consecutive_publish_failures"] = 0
        data["last_publish_error"] = None
        data["items_published"] = int(data.get("items_published") or 0) + 1

        if is_live_test:
            data["last_live_test_at"] = now_iso
            data["live_test_count"] = int(data.get("live_test_count") or 0) + 1

        self._save_health(data)

    def record_publish_failure(self, error: str, max_consecutive_failures: int = 3) -> None:
        """Records publish failure and triggers safety pause if limit reached."""
        data = self._load_health()
        now_iso = datetime.now(timezone.utc).isoformat()
        clean_err = redact_token(error)

        failures = int(data.get("consecutive_publish_failures") or 0) + 1
        data["consecutive_publish_failures"] = failures
        data["last_publish_error"] = clean_err
        data["last_error"] = clean_err
        data["items_failed"] = int(data.get("items_failed") or 0) + 1

        if failures >= max_consecutive_failures:
            data["production_paused"] = True
            data["pause_reason"] = "CONSECUTIVE_PUBLISH_FAILURES"

        self._save_health(data)

    def reset_production_state(self) -> Dict[str, Any]:
        """Safely resets temporary production pause state & failure counters."""
        data = self._load_health()
        data["consecutive_publish_failures"] = 0
        data["production_paused"] = False
        data["pause_reason"] = None
        data["live_test_count"] = 0
        data["last_publish_error"] = None
        self._save_health(data)
        return data

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

    def get_production_health_summary(self) -> Dict[str, Any]:
        """Returns structured production health diagnosis (HEALTHY, DEGRADED, PAUSED, STOPPED)."""
        data = self._load_health()
        status = data.get("status", "STOPPED")
        paused = data.get("production_paused", False)

        if paused:
            health_label = "PAUSED"
        elif status == "RUNNING":
            health_label = "DEGRADED" if (data.get("last_error") or data.get("last_publish_error")) else "HEALTHY"
        else:
            health_label = "STOPPED"

        data["health_label"] = health_label
        return data

    def reset_test_state(self) -> None:
        """Resets health state file for clean testing."""
        self._save_health(self._default_state())


def update_health_status(
    updates: Dict[str, Any],
    health_status_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Updates and persists data/health_status.json tracking operational timestamps and status."""
    if health_status_path is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        health_status_path = os.path.join(base_dir, "data", "health_status.json")

    os.makedirs(os.path.dirname(health_status_path), exist_ok=True)

    current_data = {
        "last_run": None,
        "last_success": None,
        "last_failure": None,
        "last_discovery": None,
        "last_reel": None,
        "last_meta_publish": None,
        "last_github_push": None,
        "last_error": None,
        "consecutive_failures": 0,
        "stale_status": "HEALTHY",
    }

    if os.path.exists(health_status_path):
        try:
            with open(health_status_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    current_data.update(loaded)
        except Exception:
            pass

    for key, value in updates.items():
        if key in current_data or key == "stale_status":
            if key == "last_error" and value is not None:
                current_data[key] = redact_token(str(value))
            else:
                current_data[key] = value

    temp_path = f"{health_status_path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(current_data, f, indent=2)
    os.replace(temp_path, health_status_path)
    return current_data


def get_health_status(health_status_path: Optional[str] = None) -> Dict[str, Any]:
    """Reads data/health_status.json and evaluates stale-run status."""
    if health_status_path is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        health_status_path = os.path.join(base_dir, "data", "health_status.json")

    if not os.path.exists(health_status_path):
        return {
            "last_run": None,
            "last_success": None,
            "last_failure": None,
            "last_discovery": None,
            "last_reel": None,
            "last_meta_publish": None,
            "last_github_push": None,
            "last_error": None,
            "consecutive_failures": 0,
            "stale_status": "NO_RECENT_SUCCESS",
        }

    try:
        with open(health_status_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        last_success = data.get("last_success")
        if not last_success:
            data["stale_status"] = "NO_RECENT_SUCCESS"
        return data
    except Exception:
        return {
            "last_run": None,
            "last_success": None,
            "last_failure": None,
            "last_discovery": None,
            "last_reel": None,
            "last_meta_publish": None,
            "last_github_push": None,
            "last_error": "HEALTH_READ_ERROR",
            "consecutive_failures": 0,
            "stale_status": "SYSTEM_FAILURE",
        }


def save_production_proof(
    proof_data: Dict[str, Any],
    proof_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Persists data/production_proof.json with live Reel verification evidence."""
    if proof_path is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        proof_path = os.path.join(base_dir, "data", "production_proof.json")

    os.makedirs(os.path.dirname(proof_path), exist_ok=True)

    verified = bool(proof_data.get("live_reel_verified") is True)
    clean_proof = {
        "live_reel_verified": verified,
        "status": proof_data.get("status", "LIVE_REEL_VERIFIED" if verified else "LIVE_REEL_VERIFICATION_NOT_PERFORMED"),
        "content_id": proof_data.get("content_id", ""),
        "source_url": proof_data.get("source_url", ""),
        "rights_status": proof_data.get("rights_status", ""),
        "rights_evidence_url": proof_data.get("rights_evidence_url", ""),
        "media_sha256": proof_data.get("media_sha256", ""),
        "github_raw_url": proof_data.get("github_raw_url", ""),
        "meta_creation_id": proof_data.get("meta_creation_id", ""),
        "instagram_media_id": proof_data.get("instagram_media_id", ""),
        "instagram_permalink": proof_data.get("instagram_permalink", ""),
        "published_at": proof_data.get("published_at", ""),
        "verified_at": proof_data.get("verified_at", datetime.now(timezone.utc).isoformat()),
    }

    temp_path = f"{proof_path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(clean_proof, f, indent=2)
    os.replace(temp_path, proof_path)
    return clean_proof


def get_production_proof(proof_path: Optional[str] = None) -> Dict[str, Any]:
    """Reads data/production_proof.json."""
    if proof_path is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        proof_path = os.path.join(base_dir, "data", "production_proof.json")

    if not os.path.exists(proof_path):
        return {
            "live_reel_verified": False,
            "status": "LIVE_REEL_VERIFICATION_NOT_PERFORMED",
            "content_id": "",
            "source_url": "",
            "rights_status": "",
            "rights_evidence_url": "",
            "media_sha256": "",
            "github_raw_url": "",
            "meta_creation_id": "",
            "instagram_media_id": "",
            "instagram_permalink": "",
            "published_at": "",
            "verified_at": "",
        }

    try:
        with open(proof_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "live_reel_verified": False,
            "status": "LIVE_REEL_VERIFICATION_NOT_PERFORMED",
            "content_id": "",
            "source_url": "",
            "rights_status": "",
            "rights_evidence_url": "",
            "media_sha256": "",
            "github_raw_url": "",
            "meta_creation_id": "",
            "instagram_media_id": "",
            "instagram_permalink": "",
            "published_at": "",
            "verified_at": "",
        }

