import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from config import Config
from instagram_client import InstagramAPIClient
from instagram_content_normalizer import InstagramContentNormalizer
from instagram_caption_generator import InstagramCaptionGenerator
from instagram_health import InstagramHealthTracker
from instagram_media_acquirer import InstagramMediaAcquirer
from instagram_media_deduplicator import InstagramMediaDeduplicator
from instagram_pipeline import InstagramContentPipeline, PipelineResult
from instagram_production_audit import InstagramProductionAuditStore
from instagram_production_gate import InstagramProductionGate
from security import redact_token

logger = logging.getLogger("InstagramLiveTestRunner")


@dataclass
class LiveTestResult:
    success: bool
    message: str
    content_id: str = ""
    media_type: str = ""
    creation_id: str = ""
    media_id: str = ""
    dry_run: bool = True
    audit_recorded: bool = False
    details: Dict[str, Any] = field(default_factory=dict)


class InstagramLiveTestRunner:
    """Executes a strictly controlled 1-post Live Test for production verification."""

    def __init__(
        self,
        config: Optional[Config] = None,
        client: Optional[InstagramAPIClient] = None,
        health_tracker: Optional[InstagramHealthTracker] = None,
        audit_store: Optional[InstagramProductionAuditStore] = None,
    ):
        self.config = config or Config.load_from_env(validate=False)
        self.client = client or InstagramAPIClient(
            user_id=self.config.user_id,
            access_token=self.config.access_token,
            api_version=self.config.api_version,
            timeout=self.config.timeout_seconds,
        )
        self.health_tracker = health_tracker or InstagramHealthTracker()
        self.audit_store = audit_store or InstagramProductionAuditStore()
        self.gate = InstagramProductionGate(config=self.config, health_tracker=self.health_tracker)

    def run_live_test(self, test_item: Optional[Dict[str, Any]] = None) -> LiveTestResult:
        """Executes a single controlled Live Test post."""
        start_time = time.time()
        health_data = self.health_tracker.get_health_summary()
        current_live_tests = int(health_data.get("live_test_count") or 0)

        # 1. Enforce live-test limit
        if current_live_tests >= self.config.max_live_test_posts:
            msg = (
                f"LIVE TEST LIMIT REACHED ({current_live_tests}/{self.config.max_live_test_posts}). "
                "NO ADDITIONAL POST PUBLISHED."
            )
            logger.warning(msg)
            self.audit_store.record_audit(
                content_id="live-test-limit",
                media_type="UNKNOWN",
                category="test",
                status="BLOCKED",
                error_type=msg,
                dry_run=self.config.dry_run,
                production_mode="LIVE_TEST",
            )
            return LiveTestResult(success=False, message=msg, dry_run=self.config.dry_run)

        # 2. Gate evaluation
        gate_res = self.gate.evaluate(self.config, self.health_tracker, is_live_test=True)
        if not gate_res.can_publish and not self.config.dry_run:
            msg = f"PRODUCTION GATE BLOCKED LIVE TEST: {', '.join(gate_res.reasons)}"
            logger.error(msg)
            self.audit_store.record_audit(
                content_id="live-test-gate",
                media_type="UNKNOWN",
                category="test",
                status="BLOCKED",
                error_type=msg,
                dry_run=self.config.dry_run,
                production_mode="LIVE_TEST",
            )
            return LiveTestResult(success=False, message=msg, dry_run=self.config.dry_run)

        # 3. Prepare test item
        item = test_item or {
            "content_id": "live-test-001",
            "title": "Live Test Verification Post",
            "summary": "Controlled live test post verifying Instagram API connection and publishing pipeline.",
            "category": "technology",
            "media_type": "IMAGE",
            "image_url": self.config.test_image_url or "https://i.ytimg.com/vi/pbYX4gp_5kE/maxresdefault.jpg",
        }

        normalizer = InstagramContentNormalizer()
        norm_item = normalizer.normalize(item)
        content_id = (norm_item.metadata or {}).get("content_id", "live-test-001")
        media_type = norm_item.media_type or "IMAGE"
        category = norm_item.category or "technology"

        # 4. Media & Caption Generation
        url = norm_item.image_url if media_type == "IMAGE" else norm_item.video_url
        if not url:
            url = self.config.test_image_url or "https://i.ytimg.com/vi/pbYX4gp_5kE/maxresdefault.jpg"
            if media_type == "IMAGE":
                norm_item.image_url = url
            else:
                norm_item.video_url = url

        try:
            acquirer = InstagramMediaAcquirer()
            asset = acquirer.acquire_media(url=url, media_type=media_type)
        except Exception as acq_err:
            msg = f"Media acquisition failed for live test: {acq_err}"
            self.audit_store.record_audit(
                content_id=content_id,
                media_type=media_type,
                category=category,
                status="FAILED",
                error_type=msg,
                duration=time.time() - start_time,
                dry_run=self.config.dry_run,
                production_mode="LIVE_TEST",
            )
            return LiveTestResult(success=False, message=msg, content_id=content_id, media_type=media_type)

        caption_gen = InstagramCaptionGenerator()
        caption = caption_gen.generate_caption(
            title=norm_item.title or "Live Test",
            summary=norm_item.summary or "Live Test Summary",
            category=category,
            source="TechCricketHub Live Test",
        )

        from instagram_pipeline import InstagramContent
        pipeline = InstagramContentPipeline(dry_run=self.config.dry_run)
        content_obj = InstagramContent(
            title=norm_item.title or "Live Test",
            summary=norm_item.summary or "Live Test Summary",
            category=category,
            media_type=media_type,
            image_url=norm_item.image_url,
            video_url=norm_item.video_url,
            caption=caption,
            metadata={"content_id": content_id},
        )
        pipeline_res: PipelineResult = pipeline.process_content(content_obj)

        duration = time.time() - start_time

        if pipeline_res.success:
            self.health_tracker.record_publish_success(
                media_id=pipeline_res.media_id or "dry-run-id",
                is_live_test=True,
            )
            self.audit_store.record_audit(
                content_id=content_id,
                media_type=media_type,
                category=category,
                status="PUBLISHED" if not self.config.dry_run else "VALIDATED",
                creation_id=pipeline_res.creation_id or "",
                media_id=pipeline_res.media_id or "",
                duration=duration,
                dry_run=self.config.dry_run,
                production_mode="LIVE_TEST",
            )
            msg = (
                f"Live Test successful ({'Dry Run' if self.config.dry_run else 'REAL Live Publish'}). "
                f"Creation ID: {pipeline_res.creation_id}, Media ID: {pipeline_res.media_id}"
            )
            return LiveTestResult(
                success=True,
                message=msg,
                content_id=content_id,
                media_type=media_type,
                creation_id=pipeline_res.creation_id or "",
                media_id=pipeline_res.media_id or "",
                dry_run=self.config.dry_run,
                audit_recorded=True,
                details={"status": pipeline_res.status, "message": pipeline_res.message},
            )
        else:
            self.health_tracker.record_publish_failure(
                error=pipeline_res.message or "Pipeline execution failure",
                max_consecutive_failures=self.config.max_consecutive_publish_failures,
            )
            self.audit_store.record_audit(
                content_id=content_id,
                media_type=media_type,
                category=category,
                status="FAILED",
                error_type=pipeline_res.message or "Live test failed",
                duration=duration,
                dry_run=self.config.dry_run,
                production_mode="LIVE_TEST",
            )
            return LiveTestResult(
                success=False,
                message=f"Live Test failed: {pipeline_res.message}",
                content_id=content_id,
                media_type=media_type,
                dry_run=self.config.dry_run,
                audit_recorded=True,
            )
