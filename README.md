# TechCricketHub Instagram Automation (Phases 1 - 11)

Clean, secure, and completely independent Python application for automating Instagram Business operations using Meta's Graph API (`https://graph.instagram.com/v26.0/`).

---

## Scope & Capabilities

### Phase 1: Foundation
- **Clean Project Structure**: Dedicated directory at `D:\Instagram_Agent` with isolated virtual environment.
- **Strict Project Isolation**: Zero dependencies on, or integration with, external projects.
- **Config & Environment Management**: Validates required configuration keys (`INSTAGRAM_USER_ID`, `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_API_VERSION`, `INSTAGRAM_TIMEOUT_SECONDS`, `LOG_LEVEL`, `INSTAGRAM_DRY_RUN`).
- **Security & Redaction**: Built-in redaction utilities (`security.py`) and log formatters ensuring access tokens never appear in logs, tracebacks, or console outputs.
- **Custom Exceptions**: Dedicated exception hierarchy (`InstagramError`, `InstagramConfigError`, `InstagramAPIError`, `InstagramConnectionError`, `InstagramTimeoutError`).
- **Meta Graph API Client**: `InstagramAPIClient` wrapping GET/POST HTTP methods, error response parsing, and timeout/retry protection.

### Phase 2: Image Publishing
- **Image Publishing Pipeline (`instagram_publisher.py`)**: `InstagramImagePublisher` implementing the 2-step Meta container creation & publishing workflow.
- **Strict URL Validation**: Enforces HTTPS, blocks local file paths (`C:\...`), search engine result URLs (Google/Bing), localhost, and non-image endpoints.
- **Structured Result Handling**: `PublishResult` dataclass (`success`, `creation_id`, `media_id`, `message`).
- **CLI Image Test Command**: Executable CLI script (`main.py --test-image`).

### Phase 3: Reels / Video Publishing
- **Reels Publishing Pipeline (`instagram_reel_publisher.py`)**: `InstagramReelPublisher` implementing container creation (`media_type=REELS`), container status polling, and publishing.
- **Container Processing Polling**: Automatically polls `GET /{creation_id}?fields=status_code,status` for status transitions (`IN_PROGRESS` -> `FINISHED`). Handles `ERROR` and `EXPIRED` status codes with configurable polling attempts and interval.
- **Strict Video URL Validation**: Enforces HTTPS, rejects Windows/Linux local file paths (`C:\...`, `/home/...`), loopback addresses (`localhost`, `127.0.0.1`), search result URLs, and webpage endpoints.
- **CLI Reel Test Command**: Executable CLI script (`main.py --test-reel`).

### Phase 4: Caption & Content Intelligence
- **Caption Generation Service (`instagram_caption_generator.py`)**: `InstagramCaptionGenerator` constructs structured captions with category-based hooks, informative summaries, call-to-action prompts, and normalized hashtags.
- **Category Hashtag Engine**: `HashtagGenerator` generates normalized, category-specific tags (`cricket`, `technology`, `entertainment`, `sports`, `general news`). Always includes `#TechCricketHub`, deduplicates, and caps tag count (max 30).
- **Content Sanitization**: `ContentSanitizer` strips access tokens using `security.py`, cleans control characters, normalizes line breaks, and preserves emojis.
- **Caption Validation**: `CaptionValidator` enforces Instagram rules (max 2200 characters, max 30 hashtags, no token leaks, duplicate word/hashtag spam detection).
- **Caption Preview CLI**: `main.py --preview-caption` previews generated captions without posting (`NO POST WAS PUBLISHED`).

### Phase 5: Content-to-Publishing Pipeline
- **End-to-End Pipeline (`instagram_pipeline.py`)**: `InstagramContentPipeline` orchestrates structured content input (`InstagramContent`) through validation, sanitization, caption generation, hashtag generation, media URL verification, and publishing decisioning.
- **Structured Input & Output Models**: `InstagramContent` and `PipelineResult` dataclasses with built-in secret redaction.
- **DRY_RUN Mode Default (`INSTAGRAM_DRY_RUN=true`)**: Enabled by default to prevent accidental real Instagram API publishing. Full validation and preparation steps execute, but API publish calls are safely skipped unless `INSTAGRAM_DRY_RUN=false` is explicitly configured.

### Phase 6: Content & Media Acquisition Layer
- **Content Source Abstraction (`instagram_content_source.py` & `local_content_source.py`)**: Generic interface `InstagramContentSource` and `LocalContentSource` reading sample content items from `data/sample_content.json`. Standalone implementation with **zero Telegram dependencies**.
- **Content Normalizer (`instagram_content_normalizer.py`)**: `InstagramContentNormalizer` transforms raw dictionary payloads into validated `InstagramContent` models, handling whitespace normalization, category mapping, and media type validation (`IMAGE` / `REEL`).
- **Media Acquisition & Metadata (`instagram_media_acquirer.py` & `instagram_media_metadata.py`)**: `InstagramMediaAcquirer` performs lightweight HTTP `HEAD` requests to verify status, `Content-Type`, and `Content-Length` without downloading full media payloads. Produces structured `MediaAsset` metadata.
- **Duplicate Media Detection (`instagram_media_deduplicator.py`)**: `InstagramMediaDeduplicator` tracks processed content IDs and URL SHA-256 hashes in `data/media_history.json` to prevent re-processing identical media items.
- **Batch Processing Engine**: `process_batch()` handles content lists independently so an individual item failure does not interrupt batch processing. Returns aggregated `BatchResult`.

### Phase 7: Instagram Scheduling & Queue Management
- **Persistent Queue Engine (`instagram_queue.py`)**: `InstagramQueue` manages `InstagramQueueItem` state in `data/instagram_queue.json` supporting status transitions (`PENDING`, `SCHEDULED`, `PROCESSING`, `PUBLISHED`, `FAILED`, `CANCELLED`, `DUPLICATE`, `SKIPPED`). Provides atomic file writes, corrupted state recovery, capacity limit enforcement (`INSTAGRAM_MAX_QUEUE_SIZE=50`), and deduplication checks.
- **Instagram Scheduler (`instagram_scheduler.py`)**: `InstagramScheduler` provides process locking (`data/instagram_scheduler.lock`) with stale lock detection and recovery, timezone-aware datetime calculations (`Asia/Kolkata` default), due-time evaluation (`scheduled_at <= now`), and temporary failure retries up to `INSTAGRAM_MAX_RETRIES=3`. Respects `INSTAGRAM_DRY_RUN=true` to simulate queue execution without publishing.

### Phase 8: Instagram Continuous Automation Engine
- **Automation Engine (`instagram_automation_engine.py`)**: `InstagramAutomationEngine` unifies content discovery, normalization, media verification, deduplication, caption generation, enqueuing, scheduling, and dry-run safety decisioning into a continuous automation loop. Includes process locking (`data/instagram_automation.lock`) with stale lock auto-recovery (300s timeout) and graceful signal handling (`SIGINT`, `SIGTERM`, `Ctrl+C`).
- **Health Tracking System (`instagram_health.py`)**: `InstagramHealthTracker` persists engine state and metrics in `data/instagram_health.json` (`status`, `started_at`, `last_heartbeat`, `last_cycle_at`, `last_success_at`, `last_error`, `cycles_completed`, `items_processed`, `items_published`, `items_failed`, `uptime_seconds`).

### Phase 9: Content Intelligence & Smart Scheduling
- **Content Scoring Engine (`instagram_content_scorer.py`)**: `InstagramContentScorer` evaluates title quality, summary quality, category relevance, media quality, and completeness yielding a 0–100 score and `ContentScore` breakdown.
- **Priority System (`instagram_content_priority.py`)**: `InstagramContentPriority` classifies content into `CRITICAL` (90-100), `HIGH` (75-89), `NORMAL` (55-74), `LOW` (35-54), and `REJECT` (0-34). Rejects content below threshold.
- **Category Intelligence (`instagram_category_intelligence.py`)**: `InstagramCategoryIntelligence` uses normalized text matching and keyword weighting to assign categories (`cricket`, `technology`, `ai`, `sports`, `entertainment`, `unknown`) with a confidence score.
- **Category Balancer (`instagram_category_balancer.py`)**: `InstagramCategoryBalancer` prevents category flooding by monitoring maximum category percentage thresholds (`INSTAGRAM_MAX_CATEGORY_PERCENTAGE=40`) over recent windows.
- **Repetition Guard (`instagram_repetition_guard.py`)**: `InstagramRepetitionGuard` detects exact duplicates, near duplicates (title similarity > 0.85), repeated summaries, and media URL repeats.
- **Smart Scheduler (`instagram_smart_scheduler.py`)**: `InstagramSmartScheduler` calculates optimal future posting slots in `Asia/Kolkata` timezone across posting windows (`morning`, `afternoon`, `evening`), balances media types (`max_consecutive_reels`, `max_consecutive_images`), and ranks candidate items by score.

### Phase 10: Analytics, Performance Tracking & Adaptive Optimization
- **Analytics Event Store (`instagram_analytics.py`)**: `InstagramAnalyticsStore` records lifecycle events (`DISCOVERED`, `ACCEPTED`, `REJECTED`, `QUEUED`, `SCHEDULED`, `PROCESSING`, `PUBLISHED`, `FAILED`, `SKIPPED`, `DUPLICATE`) in `data/instagram_analytics.json` with atomic writes, secret redaction, and retention cleanup (`INSTAGRAM_ANALYTICS_RETENTION_DAYS=90`).
- **Publishing Metrics Engine (`instagram_metrics.py`)**: `InstagramMetrics` computes total counts and rates (`publish_success_rate`, `failure_rate`, `duplicate_rate`, `rejection_rate`) using safe division.
- **Category Analytics (`instagram_category_analytics.py`)**: Aggregates content counts, published, failed, success rates, and average content scores per category.
- **Media Analytics (`instagram_media_analytics.py`)**: Aggregates performance by `IMAGE` vs `REEL`.
- **Posting Window Time Analytics (`instagram_time_analytics.py`)**: Maps event timestamps to `Asia/Kolkata` local posting windows (`MORNING` 08:00–10:00, `AFTERNOON` 13:00–15:00, `EVENING` 18:00–21:00, `NIGHT`).
- **Engagement Abstraction (`instagram_engagement.py`)**: `InstagramEngagementProvider` & `LocalEngagementProvider` interface safely returning `ENGAGEMENT_DATA_UNAVAILABLE` when real API metrics do not exist (prevents fake data).
- **Adaptive Optimizer (`instagram_optimizer.py`)**: `InstagramOptimizer` evaluates local publishing performance events and produces conservative reliability recommendations for category adjustment, media mix, time slot preference, and content score thresholds. Enforces minimum sample size protection (`INSTAGRAM_ANALYTICS_MIN_SAMPLE_SIZE=10`).

### Phase 11: Production Deployment & 24/7 Runtime
- **Containerization Specification**: `Dockerfile` and `.dockerignore` for containerized Python 3.10 background service execution (`CMD ["python", "main.py", "--run"]`).
- **Background Worker Blueprint**: `Procfile` (`worker: python main.py --run`) and `render.yaml` for Render/Railway/Fly background worker deployment.
- **Production Status Telemetry**: `python main.py --production-status` and `python main.py --production-test` CLI commands.
- **24/7 Cloud Execution Capability**: Operates continuously on cloud background worker environments without requiring user's laptop to remain ON.
- **Dry-Run Safety Protected**: `INSTAGRAM_DRY_RUN=true` remains active by default on cloud deployments until explicit user approval.

---

## Installation & Setup

### 1. Requirements
- Python 3.10+
- Virtual environment (`venv`)

### 2. Environment Setup

```bash
# Navigate to project directory
cd D:\Instagram_Agent

# Activate virtual environment (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Install required dependencies
pip install -r requirements.txt
```

### 3. Configuration (.env)

Copy `.env.example` to `.env`:

```ini
INSTAGRAM_USER_ID=37982406558040899
INSTAGRAM_ACCESS_TOKEN=YOUR_ACCESS_TOKEN_HERE
INSTAGRAM_API_VERSION=v26.0
INSTAGRAM_TIMEOUT_SECONDS=30
LOG_LEVEL=INFO
INSTAGRAM_TEST_IMAGE_URL=https://i.ytimg.com/vi/pbYX4gp_5kE/maxresdefault.jpg
TEST_REEL_VIDEO_URL=https://raw.githubusercontent.com/intel-iot-devkit/sample-videos/master/person-bicycle-car-detection.mp4
INSTAGRAM_DRY_RUN=true
INSTAGRAM_SCHEDULER_ENABLED=false
INSTAGRAM_TIMEZONE=Asia/Kolkata
INSTAGRAM_POST_INTERVAL_MINUTES=30
INSTAGRAM_MAX_QUEUE_SIZE=50
INSTAGRAM_MAX_RETRIES=3
INSTAGRAM_AUTOMATION_ENABLED=false
INSTAGRAM_LOOP_INTERVAL_SECONDS=60
INSTAGRAM_HEARTBEAT_INTERVAL_SECONDS=300
INSTAGRAM_MAX_ITEMS_PER_CYCLE=10
INSTAGRAM_CONTENT_SCORE_THRESHOLD=35
INSTAGRAM_MAX_CATEGORY_PERCENTAGE=40
INSTAGRAM_CATEGORY_WINDOW_SIZE=10
INSTAGRAM_MAX_CONSECUTIVE_REELS=2
INSTAGRAM_MAX_CONSECUTIVE_IMAGES=3
INSTAGRAM_MIN_POST_INTERVAL_MINUTES=30
INSTAGRAM_MORNING_START=08:00
INSTAGRAM_MORNING_END=10:00
INSTAGRAM_AFTERNOON_START=13:00
INSTAGRAM_AFTERNOON_END=15:00
INSTAGRAM_EVENING_START=18:00
INSTAGRAM_EVENING_END=21:00
INSTAGRAM_ANALYTICS_ENABLED=true
INSTAGRAM_ANALYTICS_MIN_SAMPLE_SIZE=10
INSTAGRAM_ANALYTICS_RETENTION_DAYS=90
INSTAGRAM_OPTIMIZATION_ENABLED=true
INSTAGRAM_ANALYTICS_TIMEZONE=Asia/Kolkata
```

---

## 24/7 Cloud Deployment Guide

### Option A: Render (Recommended Background Worker)
1. Log in to [Render Dashboard](https://dashboard.render.com/).
2. Click **New +** -> **Blueprint**.
3. Connect repository `Gowtham-015/techcrickethub-instagram`.
4. Render will auto-detect `render.yaml`.
5. Configure Environment Variables in Render Dashboard (`INSTAGRAM_USER_ID`, `INSTAGRAM_ACCESS_TOKEN`).
6. Deploy! Render will run `python main.py --run` continuously 24/7.

### Option B: Docker Container
```bash
docker build -t techcrickethub-instagram .
docker run -d --name instagram-bot \
  -e INSTAGRAM_USER_ID="37982406558040899" \
  -e INSTAGRAM_ACCESS_TOKEN="YOUR_TOKEN" \
  -e INSTAGRAM_DRY_RUN="true" \
  techcrickethub-instagram
```

---

## Usage & Verification

### Running Unit Tests

Run the full test suite (173 mocked unit tests):

```bash
python -m pytest tests/ -v
```

### Running Production CLI Commands

```bash
python main.py --production-status
python main.py --production-test
python main.py --run
```

---

## Safety & Isolation Policies
- **Phase 11 is completely standalone. Telegram integration is intentionally NOT implemented.**
- `INSTAGRAM_DRY_RUN=true`, `INSTAGRAM_SCHEDULER_ENABLED=false`, and `INSTAGRAM_AUTOMATION_ENABLED=false` are **enabled by default**.
- Access tokens are strictly redacted (`[REDACTED]`) across all logs, exceptions, formatters, sanitizers, validators, `PipelineResult`, `InstagramQueueItem`, `InstagramHealthTracker`, `InstagramAnalyticsEvent`, and representation methods.
- `.env` is ignored by Git and must never be committed.
