import json
import os
import tempfile
import unittest
from datetime import datetime, timezone, timedelta

from instagram_health import InstagramHealthTracker


class TestPhase21MonitoringSelfHealing(unittest.TestCase):
    """Unit test suite for Phase 21 24/7 Monitoring & Self-Healing Anomaly Detection."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.health_path = os.path.join(self.tmp_dir.name, "instagram_health.json")
        self.tracker = InstagramHealthTracker(health_path=self.health_path)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_workflow_run_metrics_recording(self):
        """Verify record_workflow_run updates success, failure, and consecutive counters."""
        self.tracker.record_workflow_run(success=True, status_label="COMPLETED")
        data = self.tracker._load_health()
        self.assertEqual(data["workflow_runs_total"], 1)
        self.assertEqual(data["workflow_runs_failed"], 0)
        self.assertEqual(data["consecutive_failures"], 0)
        self.assertIsNotNone(data["last_successful_run"])

        self.tracker.record_workflow_run(success=False, failure_type="DISCOVERY")
        data2 = self.tracker._load_health()
        self.assertEqual(data2["workflow_runs_total"], 2)
        self.assertEqual(data2["workflow_runs_failed"], 1)
        self.assertEqual(data2["consecutive_failures"], 1)
        self.assertEqual(data2["discovery_failures"], 1)

    def test_anomaly_detection_execution_gap(self):
        """Verify detect_execution_gap triggers when last successful run is older than threshold."""
        # 8 hours ago
        past_iso = (datetime.now(timezone.utc) - timedelta(hours=8)).isoformat()
        data = self.tracker._load_health()
        data["last_successful_run"] = past_iso
        self.tracker._save_health(data)

        self.assertTrue(self.tracker.detect_execution_gap(threshold_hours=6.0))
        mon = self.tracker.get_monitoring_status()
        self.assertEqual(mon["monitoring_status"], "WARNING")
        self.assertTrue(any("ABNORMAL_EXECUTION_GAP" in a for a in mon["active_alerts"]))

    def test_anomaly_detection_repeated_failures(self):
        """Verify detection of repeated discovery, rights, and Meta failures."""
        for _ in range(3):
            self.tracker.record_discovery_failure()
            self.tracker.record_meta_failure()
            self.tracker.record_duplicate_rejection()
            self.tracker.record_no_valid_reel_run(rights_rejections=1)

        self.assertTrue(self.tracker.detect_repeated_discovery_failures(threshold=3))
        self.assertTrue(self.tracker.detect_repeated_rights_failures(threshold=3))
        self.assertTrue(self.tracker.detect_repeated_meta_failures(threshold=3))
        self.assertTrue(self.tracker.detect_duplicate_protection_failures(threshold=3))
        self.assertTrue(self.tracker.detect_repeated_no_content(threshold=3))

        mon = self.tracker.get_monitoring_status()
        self.assertIn(mon["monitoring_status"], ("WARNING", "DEGRADED"))
        self.assertTrue(len(mon["active_alerts"]) >= 4)


if __name__ == "__main__":
    unittest.main()
