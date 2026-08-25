import os
import pytest
from instagram_cloud_runtime import InstagramCloudRuntime
from instagram_final_publish_guard import InstagramFinalPublishGuard
from instagram_content_bundle import ContentBundle


def test_cloud_runtime_simulation(tmp_path):
    """Simulates cloud worker startup, cycle executions, worker restart,

    and verifies that persistent published history survives restart cleanly.
    """
    data_dir = str(tmp_path / "data")

    # Worker 1 startup
    runtime1 = InstagramCloudRuntime(data_dir=data_dir)
    guard1 = InstagramFinalPublishGuard(data_dir=data_dir)

    b1 = ContentBundle(
        content_id="cloud-sim-01",
        category="cricket",
        title="Cricket World Cup Schedule Announced",
        summary="ICC announces schedule.",
        source_url="https://example.com/cwc-schedule",
        source_domain="example.com",
        published_at="2026-08-25T00:00:00Z",
        media_url="https://example.com/cwc.jpg",
        media_type="IMAGE",
        caption="Cricket World Cup Schedule Announced #Cricket",
    )

    res1 = guard1.verify_and_guard(b1)
    assert res1.is_valid
    guard1.record_published_item(bundle=b1, media_id="media-cloud-01")
    runtime1.record_cycle_complete(processed=1, published=1, failed=0)

    # Worker 2 restarts (simulating process restart)
    runtime2 = InstagramCloudRuntime(data_dir=data_dir)
    guard2 = InstagramFinalPublishGuard(data_dir=data_dir)

    # Attempt to re-publish b1 after restart
    res2 = guard2.verify_and_guard(b1)
    assert not res2.is_valid
    assert res2.error_code in ("DUPLICATE_SOURCE", "DUPLICATE_CONTENT_ID", "DUPLICATE_TITLE")

    summary = runtime2.get_runtime_summary()
    assert summary["laptop_required"] is False
    assert summary["cloud_worker_required"] is True
