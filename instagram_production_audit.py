import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from security import redact_token


class InstagramProductionAuditStore:
    """Persistent audit record store for Instagram production publishing events."""

    def __init__(self, audit_path: Optional[str] = None):
        if audit_path:
            self.audit_path = audit_path
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            self.audit_path = os.path.join(base_dir, "data", "instagram_production_audit.json")

    def _ensure_directory(self) -> None:
        dir_name = os.path.dirname(self.audit_path)
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name, exist_ok=True)

    def load_records(self) -> List[Dict[str, Any]]:
        """Loads audit records from disk."""
        if not os.path.exists(self.audit_path):
            return []
        try:
            with open(self.audit_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception:
            return []

    def record_audit(
        self,
        content_id: str,
        media_type: str,
        category: str,
        status: str,  # VALIDATED, SUBMITTED, PUBLISHED, FAILED, BLOCKED, DUPLICATE, SKIPPED
        creation_id: str = "",
        media_id: str = "",
        error_type: str = "",
        duration: float = 0.0,
        dry_run: bool = True,
        production_mode: str = "DRY_RUN",
    ) -> Dict[str, Any]:
        """Records a new production audit event to disk."""
        self._ensure_directory()
        records = self.load_records()

        # Sanitize error_type to remove any accidental tokens
        clean_error = redact_token(error_type) if error_type else ""

        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "content_id": content_id,
            "media_type": media_type,
            "category": category,
            "status": status,
            "creation_id": creation_id,
            "media_id": media_id,
            "error_type": clean_error,
            "duration": round(duration, 3),
            "dry_run": dry_run,
            "production_mode": production_mode,
        }

        records.append(record)

        try:
            with open(self.audit_path, "w", encoding="utf-8") as f:
                json.dump(records, f, indent=2)
        except Exception:
            pass

        return record

    def get_last_audit_record(self) -> Optional[Dict[str, Any]]:
        records = self.load_records()
        return records[-1] if records else None

    def get_summary(self) -> Dict[str, Any]:
        records = self.load_records()
        total = len(records)
        published = sum(1 for r in records if r.get("status") == "PUBLISHED")
        failed = sum(1 for r in records if r.get("status") == "FAILED")
        blocked = sum(1 for r in records if r.get("status") in ("BLOCKED", "DUPLICATE", "SKIPPED"))

        last = records[-1] if records else None

        return {
            "total_audit_events": total,
            "published_count": published,
            "failed_count": failed,
            "blocked_count": blocked,
            "last_event": last,
        }
