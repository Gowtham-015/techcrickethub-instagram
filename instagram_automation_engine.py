import json
import logging
import os
import signal
import sys
import time

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config import Config
from exceptions import InstagramConfigError, InstagramError
from instagram_analytics import InstagramAnalyticsEvent, InstagramAnalyticsStore
from instagram_caption_generator import InstagramCaptionGenerator
from instagram_category_balancer import InstagramCategoryBalancer
from instagram_category_intelligence import InstagramCategoryIntelligence
from instagram_content_normalizer import InstagramContentNormalizer
from instagram_content_priority import InstagramContentPriority
from instagram_content_scorer import InstagramContentScorer
from instagram_content_source import InstagramContentSource
from instagram_health import InstagramHealthTracker
from instagram_media_acquirer import InstagramMediaAcquirer
from instagram_media_deduplicator import InstagramMediaDeduplicator
from instagram_pipeline import InstagramContent, InstagramContentPipeline, PipelineResult
from instagram_queue import InstagramQueue, InstagramQueueItem
from instagram_repetition_guard import InstagramRepetitionGuard
from instagram_scheduler import InstagramScheduler
from instagram_smart_scheduler import InstagramSmartScheduler
from instagram_production_audit import InstagramProductionAuditStore
from instagram_production_gate import InstagramProductionGate
from local_content_source import LocalContentSource
from instagram_real_news_source import InstagramRealNewsSource
from instagram_cricket_data_provider import FallbackCricketProvider
from instagram_cricket_match_intelligence import InstagramCricketMatchIntelligence
from instagram_cricket_balancer import InstagramCricketBalancer
from instagram_source_verifier import InstagramSourceVerifier
from instagram_content_bundle import ContentBundle, ContentIntegrityValidator
from instagram_media_verifier import InstagramMediaVerifier
from security import RedactingFormatter, redact_token


class InstagramAutomationEngine:
    """Continuous Instagram Automation Engine coordinating content discovery, media acquisition,

    deduplication, category intelligence, content scoring, priority classification, repetition guard,
    smart scheduling, queue management, health monitoring, analytics event tracking, and dry-run safety.
    """

    def __init__(
        self,
        config: Optional[Config] = None,
        source: Optional[InstagramContentSource] = None,
        queue: Optional[InstagramQueue] = None,
        scheduler: Optional[InstagramScheduler] = None,
        health_tracker: Optional[InstagramHealthTracker] = None,
        analytics_store: Optional[InstagramAnalyticsStore] = None,
        lock_path: Optional[str] = None,
    ):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.lock_path = lock_path or os.path.join(base_dir, "data", "instagram_automation.lock")

        self.config = config or Config.load_from_env(validate=False)
        self.source = source or InstagramRealNewsSource(config=self.config)
        self.queue = queue or InstagramQueue(max_queue_size=self.config.max_queue_size)
        self.pipeline = InstagramContentPipeline(dry_run=self.config.dry_run)
        self.scheduler = scheduler or InstagramScheduler(
            queue=self.queue,
            pipeline=self.pipeline,
            config=self.config,
        )
        self.health_tracker = health_tracker or InstagramHealthTracker()
        self.analytics_store = analytics_store or InstagramAnalyticsStore(
            retention_days=self.config.analytics_retention_days
        )
        self.gate = InstagramProductionGate(config=self.config, health_tracker=self.health_tracker)
        self.audit_store = InstagramProductionAuditStore()

        # Phase 13 Real Content & Cricket Modules
        self.cricket_provider = FallbackCricketProvider()
        self.match_intel = InstagramCricketMatchIntelligence(provider=self.cricket_provider, config=self.config)
        self.cricket_balancer = InstagramCricketBalancer(config=self.config)
        self.source_verifier = InstagramSourceVerifier()
        self.bundle_validator = ContentIntegrityValidator()
        self.media_verifier = InstagramMediaVerifier()

        self.normalizer = InstagramContentNormalizer()
        self.acquirer = InstagramMediaAcquirer()
        self.deduplicator = InstagramMediaDeduplicator()

        # Phase 9 Intelligence Modules
        self.category_intel = InstagramCategoryIntelligence()
        self.scorer = InstagramContentScorer(score_threshold=self.config.content_score_threshold)
        self.priority = InstagramContentPriority(min_score_threshold=self.config.content_score_threshold)
        self.balancer = InstagramCategoryBalancer(
            max_category_percentage=self.config.max_category_percentage,
            window_size=self.config.category_window_size,
        )
        self.repetition_guard = InstagramRepetitionGuard()
        self.smart_scheduler = InstagramSmartScheduler(
            config=self.config,
            scheduler=self.scheduler,
        )

        self.running = False
        self.logger = logging.getLogger("InstagramAutomationEngine")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = RedactingFormatter(
                fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                token=self.config.access_token,
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

        self._setup_signal_handlers()

    def _setup_signal_handlers(self) -> None:
        """Configures OS signal handlers for graceful shutdown."""
        try:
            signal.signal(signal.SIGINT, self._handle_shutdown_signal)
            signal.signal(signal.SIGTERM, self._handle_shutdown_signal)
        except (ValueError, AttributeError):
            pass

    def _handle_shutdown_signal(self, signum: int, frame: Any) -> None:
        """Signal handler callback setting running state to False for clean shutdown."""
        self.logger.info(f"Received shutdown signal ({signum}). Initiating graceful shutdown...")
        self.running = False

    def _safe_record_event(self, event_type: str, **kwargs) -> None:
        """Safely records an analytics event without throwing exceptions if analytics storage fails."""
        if not self.config.analytics_enabled:
            return
        try:
            event = InstagramAnalyticsEvent(
                event_id=str(uuid.uuid4()),
                event_type=event_type,
                timestamp=datetime.now(timezone.utc).isoformat(),
                content_id=kwargs.get("content_id"),
                category=kwargs.get("category", "cricket"),
                media_type=kwargs.get("media_type", "IMAGE"),
                content_score=kwargs.get("content_score", 0),
                priority=kwargs.get("priority", "NORMAL"),
                scheduled_at=kwargs.get("scheduled_at", ""),
                status=kwargs.get("status", ""),
                media_id=kwargs.get("media_id"),
                creation_id=kwargs.get("creation_id"),
                error=kwargs.get("error"),
            )
            self.analytics_store.record_event(event)
            self.health_tracker.record_analytics_activity(events_added=1)
        except Exception as e:
            self.logger.warning(f"Analytics event recording error (non-fatal): {e}")

    def acquire_lock(self, stale_timeout_seconds: int = 300) -> bool:
        """Acquires an Instagram engine process lock with stale lock detection and recovery."""
        os.makedirs(os.path.dirname(self.lock_path), exist_ok=True)

        if os.path.exists(self.lock_path):
            try:
                with open(self.lock_path, "r", encoding="utf-8") as f:
                    lock_data = json.load(f)
                lock_time = float(lock_data.get("timestamp", 0))

                if time.time() - lock_time > stale_timeout_seconds:
                    self.logger.warning(
                        f"Stale engine lock detected (age: {int(time.time() - lock_time)}s). Overriding lock."
                    )
                    self.release_lock()
                else:
                    self.logger.error(
                        f"Active engine process lock found (PID: {lock_data.get('pid')}). Acquisition denied."
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
            self.logger.error(f"Failed to write engine lock file: {e}")
            return False

    def release_lock(self) -> None:
        """Safely removes the engine process lock file."""
        if os.path.exists(self.lock_path):
            try:
                os.remove(self.lock_path)
            except Exception as e:
                self.logger.error(f"Failed to remove engine lock file: {e}")

    def run_cycle(self) -> Dict[str, Any]:
        """Executes a single, isolated automation cycle: discovery, normalization, media verification,

        deduplication, category intelligence, scoring, repetition guard, smart scheduling, queueing,
        scheduled due-item processing, analytics tracking, and health recording.
        """
        cycle_start = time.time()
        self.logger.info("Starting automation cycle...")

        discovered_count = 0
        valid_count = 0
        duplicate_count = 0
        queued_count = 0
        published_count = 0
        failed_count = 0
        cycle_error: Optional[str] = None

        try:
            # 1. Content Discovery
            raw_items = self.source.get_content_items()
            discovered_count = len(raw_items) if isinstance(raw_items, list) else 0
            self.logger.info(f"Discovered {discovered_count} content items from source.")

            items_to_process = raw_items[: self.config.max_items_per_cycle]

            for raw_item in items_to_process:
                try:
                    # 2. Normalization & Source Verification
                    content = self.normalizer.normalize(raw_item)
                    content_id = (content.metadata or {}).get("content_id")
                    media_url = content.image_url if content.media_type == "IMAGE" else content.video_url

                    if isinstance(raw_item, dict):
                        ver_res = self.source_verifier.verify_item(raw_item)
                        if not ver_res.is_valid:
                            self.logger.info(f"Source verification failed for ID '{content_id}': {ver_res.reasons}")
                            failed_count += 1
                            continue

                    self._safe_record_event(
                        "DISCOVERED",
                        content_id=content_id,
                        category=content.category,
                        media_type=content.media_type,
                    )

                    # 3. Deduplication Check
                    if self.deduplicator.is_duplicate(content_id=content_id, url=media_url):
                        self.logger.info(f"Duplicate content skipped: ID '{content_id}' (URL: {media_url})")
                        duplicate_count += 1
                        self._safe_record_event(
                            "DUPLICATE",
                            content_id=content_id,
                            category=content.category,
                            media_type=content.media_type,
                        )
                        continue

                    # 4. Category Intelligence & Match Priority
                    detected_cat, conf = self.category_intel.detect_category(
                        title=content.title,
                        summary=content.summary,
                        default_category=content.category,
                    )
                    if detected_cat and detected_cat != "unknown":
                        content.category = detected_cat

                    source_url_val = getattr(content, "source_url", (content.metadata or {}).get("source_url", ""))
                    source_domain_val = getattr(content, "source_domain", (content.metadata or {}).get("source_domain", ""))

                    # 5. Media Verification & Content Bundle Integrity Check
                    if media_url and media_url.startswith("https://"):
                        m_res = self.media_verifier.verify_and_deduplicate(
                            url=media_url,
                            media_type=content.media_type,
                            content_id=content_id,
                            source_url=source_url_val,
                        )
                        if not m_res.is_valid:
                            self.logger.info(f"Media verification failed for '{content_id}': {m_res.message}")
                            failed_count += 1
                            self._safe_record_event(
                                "MEDIA_FAILED",
                                content_id=content_id,
                                category=content.category,
                                media_type=content.media_type,
                                error=m_res.message,
                            )
                            continue

                    bundle = ContentBundle(
                        content_id=content_id,
                        category=content.category,
                        title=content.title,
                        summary=content.summary,
                        source_url=source_url_val or "",
                        source_domain=source_domain_val or "",
                        published_at=getattr(content, "published_at", "") or "",
                        media_url=media_url or "",
                        media_type=content.media_type,
                        caption=content.caption or "",
                        hashtags=content.hashtags or [],
                    )
                    b_res = self.bundle_validator.validate_bundle(bundle)
                    if not b_res.is_valid:
                        self.logger.info(f"ContentBundle integrity check failed for '{content_id}': {b_res.message}")
                        failed_count += 1
                        self._safe_record_event(
                            "CONTENT_INTEGRITY_FAILED",
                            content_id=content_id,
                            category=content.category,
                            media_type=content.media_type,
                            error=b_res.message,
                        )
                        continue

                    asset = None
                    if media_url:
                        asset = self.acquirer.acquire_media(url=media_url, media_type=content.media_type)

                    # 6. Content Scoring, Match Priority & 75% Cricket Balancer
                    score_obj = self.scorer.score_content(content, asset=asset)

                    # Apply Match-Day priority multiplier
                    # 6. Content Scoring & Balance Enforcement
                    match_summary = self.match_intel.analyze_matches()
                    if match_summary.is_match_day and content.category == "cricket":
                        score_obj = self.scorer.score_content(content, asset=asset)
                        score_obj.total_score = min(100, int(score_obj.total_score * match_summary.priority_multiplier))
                    else:
                        score_obj = self.scorer.score_content(content, asset=asset)

                    balance = self.cricket_balancer.evaluate_balance(self.queue.get_all_items())
                    if balance.status == "CRICKET_DEFICIT" and content.category != "cricket":
                        self.logger.info(
                            f"Rejecting non-cricket content '{content_id}' due to CRICKET_DEFICIT "
                            f"({balance.cricket_percentage}% < {balance.target_percentage}%)."
                        )
                        failed_count += 1
                        continue

                    if balance.priority_boost_active and content.category == "cricket":
                        score_obj.total_score = min(100, int(score_obj.total_score * 1.25))
                    if score_obj.decision == "REJECT":
                        self.logger.info(
                            f"Content ID '{content_id}' rejected by ContentScorer: Score {score_obj.total_score}/100"
                        )
                        failed_count += 1
                        self._safe_record_event(
                            "REJECTED",
                            content_id=content_id,
                            category=content.category,
                            media_type=content.media_type,
                            content_score=score_obj.total_score,
                            priority=score_obj.priority_label,
                        )
                        continue

                    self._safe_record_event(
                        "ACCEPTED",
                        content_id=content_id,
                        category=content.category,
                        media_type=content.media_type,
                        content_score=score_obj.total_score,
                        priority=score_obj.priority_label,
                    )

                    # 7. Repetition Guard Check
                    existing_items = self.queue.get_all_items()
                    rep_res = self.repetition_guard.check_repetition(content, existing_items)
                    if rep_res.is_repeated:
                        self.logger.info(
                            f"Content ID '{content_id}' blocked by RepetitionGuard: {rep_res.reason}"
                        )
                        duplicate_count += 1
                        self._safe_record_event(
                            "DUPLICATE",
                            content_id=content_id,
                            category=content.category,
                            media_type=content.media_type,
                            content_score=score_obj.total_score,
                        )
                        continue

                    valid_count += 1

                    # 8. Smart Scheduling Timestamp Calculation
                    scheduled_slot = self.smart_scheduler.calculate_next_slot(
                        queue_items=existing_items,
                        media_type=content.media_type,
                    )

                    # 9. Enqueue Item
                    queue_item = InstagramQueueItem(
                        queue_id=f"q-{content_id or int(time.time())}",
                        content_id=content_id,
                        media_type=content.media_type,
                        title=content.title,
                        media_url=media_url or "",
                        caption=content.caption or "",
                        category=content.category,
                        scheduled_at=scheduled_slot.isoformat(),
                        status="PENDING",
                    )
                    self.queue.enqueue(queue_item)
                    queued_count += 1

                    self._safe_record_event(
                        "QUEUED",
                        content_id=content_id,
                        category=content.category,
                        media_type=content.media_type,
                        content_score=score_obj.total_score,
                        priority=score_obj.priority_label,
                        scheduled_at=scheduled_slot.isoformat(),
                    )

                    self.logger.info(f"Enqueued item '{queue_item.queue_id}' (Score: {score_obj.total_score}).")

                except InstagramError as e:
                    failed_count += 1
                    self.logger.warning(f"Item processing error: {redact_token(str(e))}")
                except Exception as e:
                    failed_count += 1
                    self.logger.warning(f"Unexpected item processing error: {redact_token(str(e))}")

            # 10. Process Due Items via Scheduler (respects INSTAGRAM_DRY_RUN & rate limits)
            limit = getattr(self.config, "max_posts_per_cycle", 1)
            scheduler_results: List[PipelineResult] = self.scheduler.process_due_items(limit=limit, force_due=True)

            due_processed = len(scheduler_results)
            for res in scheduler_results:
                if res.success:
                    if res.dry_run:
                        self._safe_record_event(
                            "SKIPPED",
                            category="cricket",
                            media_type=res.media_type,
                            status="SKIPPED",
                        )
                        self.audit_store.record_audit(
                            content_id=getattr(res, "content_id", "scheduled-item"),
                            media_type=res.media_type,
                            category="cricket",
                            status="SKIPPED",
                            creation_id=res.creation_id or "",
                            media_id=res.media_id or "",
                            dry_run=True,
                            production_mode="DRY_RUN",
                        )
                    else:
                        published_count += 1
                        self.health_tracker.record_publish_success(media_id=res.media_id or "")
                        self._safe_record_event(
                            "PUBLISHED",
                            category="cricket",
                            media_type=res.media_type,
                            media_id=res.media_id,
                            creation_id=res.creation_id,
                            status="PUBLISHED",
                        )
                        self.audit_store.record_audit(
                            content_id=getattr(res, "content_id", "scheduled-item"),
                            media_type=res.media_type,
                            category="cricket",
                            status="PUBLISHED",
                            creation_id=res.creation_id or "",
                            media_id=res.media_id or "",
                            dry_run=False,
                            production_mode="PRODUCTION",
                        )
                else:
                    failed_count += 1
                    self.health_tracker.record_publish_failure(
                        error=res.message or "Scheduler execution failure",
                        max_consecutive_failures=getattr(self.config, "max_consecutive_publish_failures", 3),
                    )
                    self._safe_record_event(
                        "FAILED",
                        category="cricket",
                        media_type=res.media_type,
                        error=res.message,
                        status="FAILED",
                    )
                    self.audit_store.record_audit(
                        content_id=getattr(res, "content_id", "scheduled-item"),
                        media_type=res.media_type,
                        category="cricket",
                        status="FAILED",
                        error_type=res.message or "Execution failed",
                        dry_run=self.config.dry_run,
                        production_mode="PRODUCTION" if not self.config.dry_run else "DRY_RUN",
                    )

            self.logger.info(
                f"Cycle summary: Discovered: {discovered_count}, Valid: {valid_count}, "
                f"Duplicates: {duplicate_count}, Queued: {queued_count}, "
                f"Due Processed: {due_processed}, Published: {published_count}, Failed: {failed_count}"
            )

        except Exception as e:
            cycle_error = redact_token(str(e))
            self.logger.error(f"Cycle execution error: {cycle_error}")

        # 11. Record metrics in Health Tracker
        self.health_tracker.record_cycle(
            processed=valid_count,
            published=published_count,
            failed=failed_count,
            error=cycle_error,
        )

        return {
            "discovered": discovered_count,
            "valid": valid_count,
            "duplicates": duplicate_count,
            "queued": queued_count,
            "published": published_count,
            "failed": failed_count,
            "error": cycle_error,
            "duration_seconds": round(time.time() - cycle_start, 2),
            "dry_run": self.config.dry_run,
        }

    def run(self) -> None:
        """Starts the continuous automation loop until stopped or interrupted."""
        if not self.acquire_lock():
            self.logger.error("Could not acquire engine lock. Exiting engine.")
            return

        self.running = True
        self.health_tracker.set_status("RUNNING")
        self.logger.info(
            f"Instagram Automation Engine STARTED. Loop interval: {self.config.loop_interval_seconds}s, "
            f"Dry Run: {self.config.dry_run}"
        )

        try:
            while self.running:
                self.run_cycle()
                self.health_tracker.update_heartbeat()

                sleep_start = time.time()
                while self.running and (time.time() - sleep_start < self.config.loop_interval_seconds):
                    time.sleep(0.5)

        except KeyboardInterrupt:
            self.logger.info("KeyboardInterrupt received. Stopping engine loop...")
        finally:
            self.running = False
            self.health_tracker.set_status("STOPPED")
            self.release_lock()
            self.logger.info("Instagram Automation Engine STOPPED cleanly.")
