import os
import pytest
from instagram_cloud_health import InstagramCloudHealth
from instagram_cloud_storage import LocalStorageProvider, get_storage_provider
from instagram_publish_lock import InstagramPublishLock, InstagramPublishLockError


def test_publish_lock_acquisition_and_release(tmp_path):
    lock_file = str(tmp_path / "test_publish.lock")
    lock1 = InstagramPublishLock(lock_file=lock_file, timeout_seconds=0.5)

    with lock1:
        assert os.path.exists(lock_file)
        # Concurrent attempt should fail
        lock2 = InstagramPublishLock(lock_file=lock_file, timeout_seconds=0.2)
        assert lock2.acquire() is False

    assert not os.path.exists(lock_file)


def test_publish_lock_stale_recovery(tmp_path):
    lock_file = str(tmp_path / "test_stale_publish.lock")
    # Create stale lock file manually
    with open(lock_file, "w") as f:
        f.write("stale_lock")

    os.utime(lock_file, (1000, 1000))  # Set past modification time

    lock = InstagramPublishLock(lock_file=lock_file, stale_threshold_seconds=1.0)
    assert lock.acquire() is True
    lock.release()


def test_cloud_storage_provider(tmp_path):
    provider = LocalStorageProvider(base_dir=str(tmp_path))
    data = {"status": "HEALTHY", "published": 5}
    assert provider.write_json("test_storage.json", data) is True
    assert provider.exists("test_storage.json") is True

    read_data = provider.read_json("test_storage.json")
    assert read_data["status"] == "HEALTHY"
    assert read_data["published"] == 5


def test_cloud_health_heartbeat(tmp_path):
    health = InstagramCloudHealth()
    summary = health.get_health_summary()
    assert summary["worker_status"] in ("STARTING", "RUNNING")
    assert "uptime_seconds" in summary
    assert "last_heartbeat" in summary
