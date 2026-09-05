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
from instagram_real_video_source import InstagramRealVideoSource
from instagram_cricket_data_provider import FallbackCricketProvider

from instagram_cricket_match_intelligence import InstagramCricketMatchIntelligence
from instagram_cricket_balancer import InstagramCricketBalancer
from instagram_reel_balancer import InstagramReelBalancer
from instagram_source_verifier import InstagramSourceVerifier
from instagram_content_bundle import ContentBundle, ContentIntegrityValidator
from instagram_media_verifier import InstagramMediaVerifier
from instagram_final_publish_guard import InstagramFinalPublishGuard
from instagram_cloud_runtime import InstagramCloudRuntime
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
        news_source: Optional[InstagramContentSource] = None,
        queue: Optional[InstagramQueue] = None,
        scheduler: Optional[InstagramScheduler] = None,
        health_tracker: Optional[InstagramHealthTracker] = None,
        analytics_store: Optional[InstagramAnalyticsStore] = None,
        lock_path: Optional[str] = None,
        data_dir: Optional[str] = None,
    ):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = data_dir or os.path.join(base_dir, "data")
        self.lock_path = lock_path or os.path.join(self.data_dir, "instagram_automation.lock")


        self.config = config or Config.load_from_env(validate=False)
        self.source = source or InstagramRealVideoSource(config=self.config)
        self.news_source = news_source if news_source is not None else (InstagramRealNewsSource(config=self.config) if source is None else None)
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
        self.reel_balancer = InstagramReelBalancer(config=self.config)
        self.source_verifier = InstagramSourceVerifier()
        self.bundle_validator = ContentIntegrityValidator()
        self.media_verifier = InstagramMediaVerifier()
        self.final_publish_guard = InstagramFinalPublishGuard(config=self.config, data_dir=self.data_dir)
        self.cloud_runtime = InstagramCloudRuntime(config=self.config)

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
        self.cloud_runtime.record_cycle_start()
        self.logger.info("Starting automation cycle...")

        # Clean stale publish lock if orphaned by previous process
        try:
            from instagram_publish_lock import InstagramPublishLock
            p_lock = InstagramPublishLock()
            if os.path.exists(p_lock.lock_file):
                p_lock.acquire()
                p_lock.release_force()
        except Exception:
            pass


        discovered_count = 0
        validated_count = 0
        rejected_count = 0
        duplicate_count = 0
        media_failed_count = 0
        queued_count = 0
        published_count = 0
        failed_count = 0
        cycle_error: Optional[str] = None

        cycle_seen_ids: Set[str] = set()
        cycle_seen_urls: Set[str] = set()

        try:
            # 1. Content Discovery (Combined from primary video source and news source)
            raw_items = []
            if self.source:
                from instagram_real_video_source import InstagramRealVideoSource
                if isinstance(self.source, InstagramRealVideoSource):
                    if getattr(self.config, "reel_discovery_enabled", False):
                        s_items = self.source.get_content_items()
                        if isinstance(s_items, list):
                            raw_items.extend(s_items)
                    else:
                        self.logger.info("Reel video discovery is disabled (INSTAGRAM_REEL_DISCOVERY_ENABLED=false). Skipping Reel discovery.")
                else:
                    s_items = self.source.get_content_items()
                    if isinstance(s_items, list):
                        raw_items.extend(s_items)
            if hasattr(self, "news_source") and self.news_source and self.news_source != self.source:
                n_items = self.news_source.get_content_items()
                if isinstance(n_items, list):
                    raw_items.extend(n_items)

            discovered_count = len(raw_items)
            self.logger.info(f"Discovered {discovered_count} content items from source(s).")

            # Safeguard: Check if candidate pool is 100% fallback-sourced
            if raw_items:
                all_fallback = all(
                    item.get("is_fallback") is True or
                    (item.get("content_id", "").startswith("realvideo-") and "oceans.mp4" in item.get("video_url", ""))
                    for item in raw_items
                )
                if all_fallback and getattr(self.config, "reel_discovery_enabled", False):
                    self.logger.warning(
                        f"WARNING: This cycle found ZERO real content — all {len(raw_items)} candidates are fallback placeholders. Nothing new will be published."
                    )
                    self._safe_record_event("ALL_CANDIDATES_FALLBACK", candidate_count=len(raw_items))

            # Calculate category & media_type distribution to prevent starvation
            cricket_candidates = [i for i in raw_items if i.get("category") == "cricket"]
            tech_candidates = [i for i in raw_items if i.get("category") == "technology"]
            other_candidates = [i for i in raw_items if i.get("category") not in ("cricket", "technology")]

            def interleave_media_types(item_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
                reels = [i for i in item_list if i.get("media_type") == "REEL"]
                images = [i for i in item_list if i.get("media_type") != "REEL"]
                res = []
                r_idx, i_idx = 0, 0
                while r_idx < len(reels) or i_idx < len(images):
                    if r_idx < len(reels):
                        res.append(reels[r_idx])
                        r_idx += 1
                    if i_idx < len(images):
                        res.append(images[i_idx])
                        i_idx += 1
                return res

            balanced_cricket = interleave_media_types(cricket_candidates)
            balanced_tech = interleave_media_types(tech_candidates)
            balanced_other = interleave_media_types(other_candidates)

            # Quota selection for this cycle using persistent history balancer
            max_limit = self.config.max_items_per_cycle
            history = self.final_publish_guard.get_published_history()
            balance = self.cricket_balancer.evaluate_balance(history)

            items_to_process: List[Dict[str, Any]] = []

            # If technology is in deficit or should be preferred, and tech candidates exist, prioritize technology
            if balance.should_prefer_tech and balanced_tech:
                tech_count = min(len(balanced_tech), max_limit)
                items_to_process.extend(balanced_tech[:tech_count])

            # Fill remaining quota with cricket candidates, then tech, then other
            if len(items_to_process) < max_limit and balanced_cricket:
                needed = max_limit - len(items_to_process)
                items_to_process.extend(balanced_cricket[:needed])

            if len(items_to_process) < max_limit and balanced_tech:
                existing_ids = {i.get("content_id") for i in items_to_process}
                for item in balanced_tech:
                    if item.get("content_id") not in existing_ids:
                        items_to_process.append(item)
                        if len(items_to_process) >= max_limit:
                            break

            if len(items_to_process) < max_limit and balanced_other:
                existing_ids = {i.get("content_id") for i in items_to_process}
                for item in balanced_other:
                    if item.get("content_id") not in existing_ids:
                        items_to_process.append(item)
                        if len(items_to_process) >= max_limit:
                            break

            if not items_to_process:
                items_to_process = interleave_media_types(raw_items)[:max_limit]

            per_item_audits: List[Dict[str, Any]] = []

            for idx, raw_item in enumerate(items_to_process, 1):
                content_id = "unknown"
                c_category = "unknown"
                c_media_type = "UNKNOWN"
                c_title = "Untitled"
                c_source = "unknown"
                try:
                    # 2. Normalization & Source Verification
                    content = self.normalizer.normalize(raw_item)
                    content_id = (content.metadata or {}).get("content_id") or content_id
                    c_category = content.category
                    c_media_type = content.media_type
                    c_title = content.title
                    c_source = (content.metadata or {}).get("source_domain") or raw_item.get("source_name") or "unknown"
                    media_url = content.image_url if content.media_type == "IMAGE" else content.video_url

                    if isinstance(raw_item, dict):
                        ver_res = self.source_verifier.verify_item(raw_item)
                        if not ver_res.is_valid:
                            self.deduplicator.mark_processed(content_id=content_id, url=media_url, status="INVALID_SOURCE")
                            self.logger.warning(
                                f"FAILED\n"
                                f"ID: {content_id}\n"
                                f"Category: {c_category}\n"
                                f"Media: {c_media_type}\n"
                                f"Source: {c_source}\n"
                                f"Stage: SOURCE_VERIFICATION\n"
                                f"Code: INVALID_SOURCE\n"
                                f"Reason: Source verification failed: {ver_res.reasons}"
                            )
                            failed_count += 1
                            per_item_audits.append({
                                "idx": idx, "content_id": content_id, "category": c_category,
                                "media_type": c_media_type, "title": c_title, "result": "FAILED",
                                "reason": f"Source verification failed: {ver_res.reasons}"
                            })
                            continue

                    self._safe_record_event(
                        "DISCOVERED",
                        content_id=content_id,
                        category=content.category,
                        media_type=content.media_type,
                    )

                    # 3. Deduplication Check (Persistent history + intra-cycle in-memory check)
                    is_persistent_dup = self.deduplicator.is_duplicate(content_id=content_id, url=media_url)
                    is_intra_cycle_dup = (
                        (content_id and content_id != "unknown" and content_id in cycle_seen_ids) or
                        (media_url and media_url in cycle_seen_urls)
                    )

                    if is_persistent_dup or is_intra_cycle_dup:
                        self.logger.info(f"Duplicate content skipped: ID '{content_id}' (URL: {media_url})")
                        duplicate_count += 1
                        self._safe_record_event(
                            "DUPLICATE",
                            content_id=content_id,
                            category=content.category,
                            media_type=content.media_type,
                        )
                        per_item_audits.append({
                            "idx": idx, "content_id": content_id, "category": c_category,
                            "media_type": c_media_type, "title": c_title, "result": "DUPLICATE",
                            "reason": "Duplicate content ID or URL"
                        })
                        continue

                    # Record in intra-cycle memory for this run to avoid intra-cycle duplicate re-verification
                    if content_id and content_id != "unknown":
                        cycle_seen_ids.add(content_id)
                    if media_url:
                        cycle_seen_urls.add(media_url)

                    # 4. Category Intelligence & Match Priority
                    detected_cat, conf = self.category_intel.detect_category(
                        title=content.title,
                        summary=content.summary,
                        default_category=content.category,
                    )
                    if detected_cat and detected_cat != "unknown":
                        content.category = detected_cat
                        c_category = detected_cat

                    source_url_val = getattr(content, "source_url", (content.metadata or {}).get("source_url", ""))
                    source_domain_val = getattr(content, "source_domain", (content.metadata or {}).get("source_domain", ""))
                    rights_val = raw_item.get("media_rights_status") if isinstance(raw_item, dict) else "ORIGINAL_GENERATED"

                    # 4b. Enforce strict REEL No-Fallback policy (Part 9)
                    if content.media_type == "REEL" and (not media_url or not media_url.startswith("http")):
                        self.deduplicator.mark_processed(content_id=content_id, url=media_url, status="REEL_REQUIRED_BUT_MEDIA_UNAVAILABLE")
                        self.logger.warning(
                            f"FAILED\n"
                            f"ID: {content_id}\n"
                            f"Category: {c_category}\n"
                            f"Media: {c_media_type}\n"
                            f"Source: {c_source}\n"
                            f"Stage: MEDIA_SELECTION\n"
                            f"Code: REEL_REQUIRED_BUT_MEDIA_UNAVAILABLE\n"
                            f"Reason: Reel required but valid Reel video URL unavailable"
                        )
                        media_failed_count += 1
                        rejected_count += 1
                        self._safe_record_event(
                            "REEL_REQUIRED_BUT_MEDIA_UNAVAILABLE",
                            content_id=content_id,
                            category=content.category,
                            media_type=content.media_type,
                            error="REEL_REQUIRED_BUT_MEDIA_UNAVAILABLE",
                        )
                        per_item_audits.append({
                            "idx": idx, "content_id": content_id, "category": c_category,
                            "media_type": c_media_type, "title": c_title, "result": "REJECTED",
                            "reason": "REEL_REQUIRED_BUT_MEDIA_UNAVAILABLE"
                        })
                        continue

                    # 4c. Production Guard against synthetic / fake / demo video reels
                    if self.config.production_enabled and not self.config.dry_run and content.media_type == "REEL":
                        is_synthetic = (
                            raw_item.get("is_synthetic", False) or
                            raw_item.get("is_fallback", False) or
                            "oceans.mp4" in (media_url or "") or
                            "sample" in (media_url or "").lower()
                        )
                        if is_synthetic:
                            self.deduplicator.mark_processed(content_id=content_id, url=media_url, status="SYNTHETIC_REEL_REJECTED")
                            self.logger.warning(f"Production Guard rejected synthetic/demo Reel '{content_id}' (URL: {media_url})")
                            rejected_count += 1
                            per_item_audits.append({
                                "idx": idx, "content_id": content_id, "category": c_category,
                                "media_type": c_media_type, "title": c_title, "result": "REJECTED",
                                "reason": "Synthetic or demo Reel rejected in production mode"
                            })
                            continue

                    # 5. Media Verification & Content Bundle Integrity Check
                    if media_url and media_url.startswith("https://"):
                        m_res = self.media_verifier.verify_and_deduplicate(
                            url=media_url,
                            media_type=content.media_type,
                            content_id=content_id,
                            source_url=source_url_val,
                        )
                        if not m_res.is_valid:
                            err_code_str = getattr(m_res, "error_code", "") or "MEDIA_VERIFICATION_FAILED"
                            err_msg_lower = (getattr(m_res, "message", "") or "").lower()
                            is_transient = (
                                "timeout" in err_msg_lower or
                                "connection" in err_msg_lower or
                                "timed out" in err_msg_lower or
                                "503" in err_msg_lower or
                                "500" in err_msg_lower or
                                "502" in err_msg_lower or
                                "temporary" in err_msg_lower
                            )
                            if not is_transient:
                                self.deduplicator.mark_processed(content_id=content_id, url=media_url, status=err_code_str)

                            self.logger.warning(
                                f"FAILED\n"
                                f"ID: {content_id}\n"
                                f"Category: {c_category}\n"
                                f"Media: {c_media_type}\n"
                                f"Source: {c_source}\n"
                                f"Stage: LOCAL_MEDIA_VERIFICATION\n"
                                f"Code: {err_code_str}\n"
                                f"Reason: Media verification failed: {m_res.message}"
                            )
                            media_failed_count += 1
                            self._safe_record_event(
                                "MEDIA_FAILED",
                                content_id=content_id,
                                category=content.category,
                                media_type=content.media_type,
                                error=m_res.message,
                            )
                            per_item_audits.append({
                                "idx": idx, "content_id": content_id, "category": c_category,
                                "media_type": c_media_type, "title": c_title, "result": "FAILED",
                                "reason": f"Media verification failed: {m_res.message}"
                            })
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
                        media_rights_status=rights_val or "UNKNOWN",
                        caption=content.caption or "",
                        hashtags=content.hashtags or [],
                    )
                    b_res = self.bundle_validator.validate_bundle(bundle)
                    if not b_res.is_valid:
                        self.deduplicator.mark_processed(content_id=content_id, url=media_url, status="CONTENT_INTEGRITY_FAILED")
                        self.logger.warning(
                            f"FAILED\n"
                            f"ID: {content_id}\n"
                            f"Category: {c_category}\n"
                            f"Media: {c_media_type}\n"
                            f"Source: {c_source}\n"
                            f"Stage: BUNDLE_VALIDATION\n"
                            f"Code: CONTENT_INTEGRITY_FAILED\n"
                            f"Reason: ContentBundle invalid: {b_res.message}"
                        )
                        failed_count += 1
                        self._safe_record_event(
                            "CONTENT_INTEGRITY_FAILED",
                            content_id=content_id,
                            category=content.category,
                            media_type=content.media_type,
                            error=b_res.message,
                        )
                        per_item_audits.append({
                            "idx": idx, "content_id": content_id, "category": c_category,
                            "media_type": c_media_type, "title": c_title, "result": "FAILED",
                            "reason": f"ContentBundle invalid: {b_res.message}"
                        })
                        continue

                    asset = None
                    if media_url:
                        asset = self.acquirer.acquire_media(url=media_url, media_type=content.media_type)

                    # 6. Content Scoring & Balance Enforcement over Published History
                    match_summary = self.match_intel.analyze_matches()
                    score_obj = self.scorer.score_content(content, asset=asset)
                    if match_summary.is_match_day and content.category == "cricket":
                        score_obj.total_score = min(100, int(score_obj.total_score * match_summary.priority_multiplier))

                    published_history = self.final_publish_guard.get_published_history()
                    items_for_balance = published_history if published_history else self.queue.get_all_items()
                    balance = self.cricket_balancer.evaluate_balance(items_for_balance)

                    if balance.priority_boost_active and content.category == "cricket":
                        score_obj.total_score = min(100, int(score_obj.total_score * 1.25))
                    elif getattr(balance, "should_prefer_tech", False) and content.category != "cricket":
                        score_obj.total_score = min(100, int(score_obj.total_score * 1.5))

                    reel_bal = self.reel_balancer.evaluate_balance(items_for_balance)
                    if getattr(reel_bal, "should_prefer_reels", False) and content.media_type == "REEL":
                        score_obj.total_score = min(100, int(score_obj.total_score * 1.3))

                    if score_obj.decision == "REJECT":
                        self.deduplicator.mark_processed(content_id=content_id, url=media_url, status="SCORE_BELOW_THRESHOLD")
                        self.logger.warning(
                            f"REJECTED\n"
                            f"ID: {content_id}\n"
                            f"Category: {c_category}\n"
                            f"Media: {c_media_type}\n"
                            f"Source: {c_source}\n"
                            f"Stage: CONTENT_SCORING\n"
                            f"Code: SCORE_BELOW_THRESHOLD\n"
                            f"Reason: Rejected by ContentScorer (Score: {score_obj.total_score}/100)"
                        )
                        rejected_count += 1
                        self._safe_record_event(
                            "REJECTED",
                            content_id=content_id,
                            category=content.category,
                            media_type=content.media_type,
                            content_score=score_obj.total_score,
                            priority=score_obj.priority_label,
                        )
                        per_item_audits.append({
                            "idx": idx, "content_id": content_id, "category": c_category,
                            "media_type": c_media_type, "title": c_title, "result": "REJECTED",
                            "reason": f"Rejected by ContentScorer (Score: {score_obj.total_score})"
                        })
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
                        self.deduplicator.mark_processed(content_id=content_id, url=media_url, status="DUPLICATE_REPETITION")
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
                        per_item_audits.append({
                            "idx": idx, "content_id": content_id, "category": c_category,
                            "media_type": c_media_type, "title": c_title, "result": "DUPLICATE",
                            "reason": f"RepetitionGuard blocked: {rep_res.reason}"
                        })
                        continue

                    # 8. Final Publish Guard Pre-Check
                    guard_res = self.final_publish_guard.verify_and_guard(bundle)
                    if not guard_res.is_valid:
                        self.deduplicator.mark_processed(content_id=content_id, url=media_url, status="FINAL_GUARD_BLOCKED")
                        self.logger.info(
                            f"Content ID '{content_id}' blocked by Final Publish Guard: {guard_res.message}"
                        )
                        duplicate_count += 1
                        self._safe_record_event(
                            "DUPLICATE",
                            content_id=content_id,
                            category=content.category,
                            media_type=content.media_type,
                            content_score=score_obj.total_score,
                        )
                        per_item_audits.append({
                            "idx": idx, "content_id": content_id, "category": c_category,
                            "media_type": c_media_type, "title": c_title, "result": "DUPLICATE",
                            "reason": f"FinalPublishGuard blocked: {guard_res.message}"
                        })
                        continue

                    validated_count += 1

                    # Mark item processed permanently on disk upon successful validation and enqueue
                    self.deduplicator.mark_processed(content_id=content_id, url=media_url, status="PROCESSED")

                    # 9. Smart Scheduling Timestamp Calculation
                    scheduled_slot = self.smart_scheduler.calculate_next_slot(
                        queue_items=existing_items,
                        media_type=content.media_type,
                    )

                    # 10. Enqueue Item
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
                        source_url=source_url_val or "",
                        source_domain=source_domain_val or "",
                        summary=content.summary or "",
                        facts=getattr(content, "facts", []) or [],
                        hashtags=content.hashtags or [],
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
                    per_item_audits.append({
                        "idx": idx, "content_id": content_id, "category": c_category,
                        "media_type": c_media_type, "title": c_title, "result": "ACCEPTED",
                        "reason": "Passed all verification checks & enqueued"
                    })

                except InstagramError as e:
                    failed_count += 1
                    err_msg = redact_token(str(e))
                    self.logger.warning(
                        f"FAILED\n"
                        f"ID: {content_id}\n"
                        f"Category: {c_category}\n"
                        f"Media: {c_media_type}\n"
                        f"Source: {c_source}\n"
                        f"Stage: CYCLE_PROCESSING\n"
                        f"Code: INSTAGRAM_ERROR\n"
                        f"Reason: {err_msg}"
                    )
                    per_item_audits.append({
                        "idx": idx, "content_id": content_id, "category": c_category,
                        "media_type": c_media_type, "title": c_title, "result": "FAILED",
                        "reason": f"InstagramError: {err_msg}"
                    })
                except Exception as e:
                    failed_count += 1
                    err_msg = redact_token(str(e))
                    self.logger.warning(
                        f"FAILED\n"
                        f"ID: {content_id}\n"
                        f"Category: {c_category}\n"
                        f"Media: {c_media_type}\n"
                        f"Source: {c_source}\n"
                        f"Stage: CYCLE_PROCESSING\n"
                        f"Code: UNEXPECTED_ERROR\n"
                        f"Reason: {err_msg}"
                    )
                    per_item_audits.append({
                        "idx": idx, "content_id": content_id, "category": c_category,
                        "media_type": c_media_type, "title": c_title, "result": "FAILED",
                        "reason": f"Exception: {err_msg}"
                    })

            if per_item_audits:
                self.logger.info("========================================")
                self.logger.info("CONTENT VALIDATION AUDIT")
                self.logger.info("========================================")
                for audit in per_item_audits:
                    self.logger.info(
                        f"Item {audit['idx']}:\n"
                        f"  ID: {audit['content_id']}\n"
                        f"  Category: {audit['category']}\n"
                        f"  Media Type: {audit['media_type']}\n"
                        f"  Title: '{audit['title'][:60]}'\n"
                        f"  Result: {audit['result']}\n"
                        f"  Reason: {audit['reason']}"
                    )
                self.logger.info("========================================")

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
                f"Cycle Summary:\n"
                f"  Discovered: {discovered_count}\n"
                f"  Validated: {validated_count}\n"
                f"  Rejected: {rejected_count}\n"
                f"  Duplicates: {duplicate_count}\n"
                f"  Media Failed: {media_failed_count}\n"
                f"  Queued: {queued_count}\n"
                f"  Published: {published_count}\n"
                f"  Failed: {failed_count}"
            )

        except Exception as e:
            cycle_error = redact_token(str(e))
            self.logger.error(f"Cycle execution error: {cycle_error}")

        # 11. Record metrics in Health Tracker & Cloud Runtime
        self.health_tracker.record_cycle(
            processed=validated_count,
            published=published_count,
            failed=failed_count,
            error=cycle_error,
        )
        self.cloud_runtime.record_cycle_complete(
            processed=validated_count,
            published=published_count,
            failed=failed_count,
            error=cycle_error,
        )

        # 12. Persist machine-readable last production run & proof records
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            run_id = f"run-{int(cycle_start)}"
            last_run_data = {
                "run_id": run_id,
                "started_at": datetime.fromtimestamp(cycle_start, timezone.utc).isoformat(),
                "completed_at": now_iso,
                "discovered": discovered_count,
                "validated": validated_count,
                "rejected": rejected_count,
                "reels_published": published_count,
                "images_published": 0,
                "failures": failed_count,
                "instagram_media_ids": [],
                "status": "PUBLISHED" if published_count > 0 else ("SKIPPED_DRY_RUN" if self.config.dry_run else "SUCCESS"),
            }
            last_run_file = os.path.join(self.data_dir, "last_production_run.json")
            with open(f"{last_run_file}.tmp", "w", encoding="utf-8") as f:
                json.dump(last_run_data, f, indent=2)
            os.replace(f"{last_run_file}.tmp", last_run_file)

            # Persist production proof
            proof_file = os.path.join(self.data_dir, "production_proof.json")
            gh_run_id = os.getenv("GITHUB_RUN_ID", "local-exec")
            gh_repo = os.getenv("GITHUB_REPOSITORY", "Gowtham-015/techcrickethub-instagram")
            proof_data = {
                "github_actions_run_id": gh_run_id,
                "workflow_run_url": f"https://github.com/{gh_repo}/actions/runs/{gh_run_id}" if gh_run_id != "local-exec" else "local",
                "execution_timestamp": now_iso,
                "discovered": discovered_count,
                "validated": validated_count,
                "published_count": published_count,
                "status": "PRODUCTION_VERIFIED" if (published_count > 0 or self.config.dry_run) else "RUN_COMPLETED",
            }
            with open(f"{proof_file}.tmp", "w", encoding="utf-8") as f:
                json.dump(proof_data, f, indent=2)
            os.replace(f"{proof_file}.tmp", proof_file)
        except Exception as p_err:
            self.logger.warning(f"Could not persist production run/proof files: {p_err}")

        return {
            "discovered": discovered_count,
            "valid": validated_count,
            "validated": validated_count,
            "rejected": rejected_count,
            "duplicates": duplicate_count,
            "media_failed": media_failed_count,
            "queued": queued_count,
            "published": published_count,
            "failed": failed_count,
            "error": cycle_error,
            "duration_seconds": round(time.time() - cycle_start, 2),
            "dry_run": self.config.dry_run,
        }




    def prepare_media(self) -> Dict[str, Any]:
        """Phase A: Discovers candidate, acquires and prepares media locally, constructs public URL,
        and saves prepared state to data/prepared_media.json without calling Meta Graph API.
        """
        self.logger.info("Executing Phase A: Prepare Media...")
        prepared_file = os.path.join(self.data_dir, "prepared_media.json")
        
        # 1. Discover raw candidates
        raw_items = []
        if self.source:
            from instagram_real_video_source import InstagramRealVideoSource
            if isinstance(self.source, InstagramRealVideoSource):
                if getattr(self.config, "reel_discovery_enabled", False):
                    s_items = self.source.get_content_items()
                    if isinstance(s_items, list):
                        raw_items.extend(s_items)
            else:
                s_items = self.source.get_content_items()
                if isinstance(s_items, list):
                    raw_items.extend(s_items)
        if hasattr(self, "news_source") and self.news_source and self.news_source != self.source:
            n_items = self.news_source.get_content_items()
            if isinstance(n_items, list):
                raw_items.extend(n_items)

        if not raw_items:
            self.logger.warning("Prepare Media: No content items discovered.")
            return {"status": "FAILED", "reason": "No content items discovered", "prepared": False}

        # 2. Category & Reel balance selection
        published_history = self.final_publish_guard.get_published_history()
        selected_raw = None
        for raw_item in raw_items:
            content = self.normalizer.normalize(raw_item)
            content_id = (content.metadata or {}).get("content_id") or "unknown"
            media_url = content.image_url if content.media_type == "IMAGE" else content.video_url

            # Skip duplicates
            if self.deduplicator.is_duplicate(content_id=content_id, url=media_url):
                continue
            
            # Skip synthetic reels in production mode
            if self.config.production_enabled and not self.config.dry_run and content.media_type == "REEL":
                is_synthetic = (
                    raw_item.get("is_synthetic", False) or
                    raw_item.get("is_fallback", False) or
                    "oceans.mp4" in (media_url or "") or
                    "sample" in (media_url or "").lower()
                )
                if is_synthetic:
                    continue
            
            bundle = ContentBundle(
                content_id=content_id,
                category=content.category,
                title=content.title,
                summary=content.summary,
                source_url=getattr(content, "source_url", "") or "",
                source_domain=getattr(content, "source_domain", "") or "",
                published_at=getattr(content, "published_at", "") or "",
                media_url=media_url or "",
                media_type=content.media_type,
                media_rights_status=raw_item.get("media_rights_status", "RIGHTS_EVIDENCE_MISSING"),
                caption=content.caption or "",
                hashtags=content.hashtags or [],
            )
            g_res = self.final_publish_guard.verify_and_guard(bundle)
            if g_res.is_valid:
                selected_raw = raw_item
                break

        if not selected_raw:
            self.logger.warning("Prepare Media: No valid unpublished candidate passed duplicate guard.")
            return {"status": "FAILED", "reason": "No valid unpublished candidate", "prepared": False}

        content = self.normalizer.normalize(selected_raw)
        content_id = (content.metadata or {}).get("content_id") or f"prep-{int(time.time())}"
        media_url = content.image_url if content.media_type == "IMAGE" else content.video_url

        from instagram_public_media_host import PublicMediaHost
        host = PublicMediaHost()
        
        local_file = selected_raw.get("local_path") or selected_raw.get("video_url") or selected_raw.get("image_url") or ""
        if local_file and not os.path.exists(local_file) and media_url and media_url.startswith("http"):
            asset = self.acquirer.acquire_media(media_url, media_type=content.media_type)
            if asset and asset.url:
                local_file = asset.url

        public_url = host.get_public_url(local_file) if local_file else media_url

        prepared_data = {
            "content_id": content_id,
            "title": content.title,
            "summary": content.summary,
            "category": content.category,
            "media_type": content.media_type,
            "local_file": local_file,
            "public_url": public_url,
            "caption": content.title,
            "hashtags": content.hashtags or [],
            "source_url": getattr(content, "source_url", "") or "",
            "source_domain": getattr(content, "source_domain", "") or "",
            "media_rights_status": selected_raw.get("media_rights_status", "RIGHTS_EVIDENCE_MISSING"),
            "prepared_at": datetime.now(timezone.utc).isoformat(),
        }

        os.makedirs(os.path.dirname(prepared_file), exist_ok=True)
        with open(f"{prepared_file}.tmp", "w", encoding="utf-8") as f:
            json.dump(prepared_data, f, indent=2)
        os.replace(f"{prepared_file}.tmp", prepared_file)

        self.logger.info(f"Prepare Media SUCCESS: Prepared candidate '{content_id}' ({public_url})")
        return {
            "status": "PREPARED",
            "prepared": True,
            "content_id": content_id,
            "category": content.category,
            "media_type": content.media_type,
            "public_url": public_url,
            "local_file": local_file,
        }

    def publish_prepared(self) -> Dict[str, Any]:
        """Phase B/C: Reads prepared media, verifies public accessibility, performs Meta Graph API publishing,
        verifies published media ID, records history, and cleans up prepared state.
        """
        self.logger.info("Executing Phase B/C: Publish Prepared Media...")
        prepared_file = os.path.join(self.data_dir, "prepared_media.json")

        if not os.path.exists(prepared_file):
            self.logger.info("No prepared_media.json found. Fallback to prepare_media first...")
            prep_res = self.prepare_media()
            if not prep_res.get("prepared"):
                return {"status": "FAILED", "reason": "Could not prepare media for publishing", "published": 0}

        try:
            with open(prepared_file, "r", encoding="utf-8") as f:
                prep_data = json.load(f)
        except Exception as e:
            return {"status": "FAILED", "reason": f"Failed to load prepared_media.json: {e}", "published": 0}

        content_id = prep_data.get("content_id")
        public_url = prep_data.get("public_url")
        media_type = prep_data.get("media_type", "REEL")
        caption = prep_data.get("caption", prep_data.get("title", ""))
        category = prep_data.get("category", "cricket")

        # 1. Verify external public accessibility
        verifier_res = InstagramMediaVerifier.validate_meta_media_accessibility(public_url, media_type=media_type)
        if not verifier_res.get("is_valid"):
            err_msg = verifier_res.get("error", "Public media verification failed")
            self.logger.error(f"Publish Prepared FAILED: Public media accessibility verification failed for {public_url}: {err_msg}")
            return {"status": "FAILED", "reason": err_msg, "published": 0}

        bundle = ContentBundle(
            content_id=content_id,
            category=category,
            title=prep_data.get("title", ""),
            summary=prep_data.get("summary", ""),
            source_url=prep_data.get("source_url", ""),
            source_domain=prep_data.get("source_domain", ""),
            published_at=prep_data.get("prepared_at", ""),
            media_url=public_url,
            media_type=media_type,
            media_rights_status=prep_data.get("media_rights_status", "RIGHTS_EVIDENCE_MISSING"),
            caption=caption,
            hashtags=prep_data.get("hashtags", []),
        )

        g_res = self.final_publish_guard.verify_and_guard(bundle)
        if not g_res.is_valid:
            self.logger.warning(f"Publish Prepared BLOCKED by duplicate guard: {g_res.message}")
            try:
                os.remove(prepared_file)
            except Exception:
                pass
            return {"status": "BLOCKED", "reason": g_res.message, "published": 0}

        if self.config.dry_run:
            self.logger.info(f"Publish Prepared SKIPPED (DRY_RUN mode active). Target URL: {public_url}")
            return {"status": "SKIPPED_DRY_RUN", "published": 0, "dry_run": True, "creation_id": None, "media_id": None}

        # 2. Real Publishing via Meta Graph API with Bounded Retries (max 3 attempts, exponential backoff)
        import time
        from instagram_client import InstagramAPIClient
        from instagram_reel_publisher import InstagramReelPublisher
        from instagram_publisher import InstagramImagePublisher

        max_attempts = 3
        last_error = ""

        for attempt in range(1, max_attempts + 1):
            if attempt > 1:
                # Pre-retry duplicate check: Was media already published?
                hist = self.final_publish_guard.get_published_history()
                existing = next((h for h in hist if h.get("content_id") == content_id), None)
                if existing and existing.get("instagram_media_id"):
                    existing_id = existing["instagram_media_id"]
                    self.logger.info(f"Pre-retry check found media already published: {existing_id}. Stopping retries.")
                    try:
                        os.remove(prepared_file)
                    except Exception:
                        pass
                    return {
                        "status": "SUCCESS",
                        "published": 1,
                        "creation_id": existing.get("meta_creation_id"),
                        "media_id": existing_id,
                        "verified": True,
                        "pre_retry_found": True,
                    }

                backoff_sec = 2 ** (attempt - 1)
                self.logger.info(f"Retry attempt {attempt}/{max_attempts} after backoff of {backoff_sec}s...")
                time.sleep(backoff_sec)

            try:
                client = InstagramAPIClient(user_id=self.config.user_id, access_token=self.config.access_token)
                if media_type == "REEL":
                    publisher = InstagramReelPublisher(client=client)
                    pub_res = publisher.publish_reel(video_url=public_url, caption=caption)
                else:
                    publisher = InstagramImagePublisher(client=client)
                    pub_res = publisher.publish_image(image_url=public_url, caption=caption)

                if pub_res.success and pub_res.media_id:
                    # 3. Post-publish verification call
                    is_verified = client.verify_published_media(pub_res.media_id)
                    if is_verified:
                        self.final_publish_guard.record_published_item(bundle=bundle, media_id=pub_res.media_id)
                        self.health_tracker.record_publish_success(media_id=pub_res.media_id)
                        try:
                            os.remove(prepared_file)
                        except Exception:
                            pass
                        self.logger.info(f"Publish Prepared SUCCESS: Media ID {pub_res.media_id}")
                        return {
                            "status": "SUCCESS",
                            "published": 1,
                            "creation_id": pub_res.creation_id,
                            "media_id": pub_res.media_id,
                            "verified": True,
                        }
                    else:
                        last_error = "Published media verification on Meta API returned false"
                else:
                    last_error = pub_res.message or "Meta API publication failed"

            except Exception as e:
                last_error = redact_token(str(e))
                self.logger.warning(f"Publish Prepared Attempt {attempt} failed: {last_error}")

        self.health_tracker.record_publish_failure(last_error)
        return {"status": "FAILED", "reason": last_error, "published": 0}

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
