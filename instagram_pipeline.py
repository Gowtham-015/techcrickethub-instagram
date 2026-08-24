import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from config import Config
from exceptions import InstagramConfigError, InstagramError
from instagram_caption_generator import (
    CaptionValidator,
    ContentSanitizer,
    HashtagGenerator,
    InstagramCaptionGenerator,
)
from instagram_client import InstagramAPIClient
from instagram_content_normalizer import InstagramContentNormalizer
from instagram_media_acquirer import InstagramMediaAcquirer
from instagram_media_deduplicator import InstagramMediaDeduplicator
from instagram_publisher import InstagramImagePublisher
from instagram_reel_publisher import InstagramReelPublisher
from security import RedactingFormatter, redact_token


@dataclass
class InstagramContent:
    """Structured content input container for the Instagram automation pipeline."""

    title: str
    summary: str
    category: str = "cricket"
    source: Optional[str] = None
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    caption: Optional[str] = None
    hashtags: Optional[List[str]] = None
    media_type: str = "IMAGE"
    metadata: Optional[Dict[str, Any]] = field(default_factory=dict)


@dataclass
class PipelineResult:
    """Structured result object for content pipeline processing."""

    success: bool
    dry_run: bool
    media_type: str
    caption: str = ""
    hashtags: List[str] = field(default_factory=list)
    creation_id: Optional[str] = None
    media_id: Optional[str] = None
    status: str = ""
    message: str = ""
    error: Optional[str] = None

    def __repr__(self) -> str:
        safe_msg = redact_token(self.message)
        safe_err = redact_token(self.error) if self.error else None
        return (
            f"PipelineResult(success={self.success}, dry_run={self.dry_run}, "
            f"media_type={self.media_type!r}, creation_id={self.creation_id!r}, "
            f"media_id={self.media_id!r}, status={self.status!r}, "
            f"message={safe_msg!r}, error={safe_err!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()


@dataclass
class BatchResult:
    """Dataclass holding summary metrics for batch content processing."""

    total: int
    successful: int
    failed: int
    duplicates: int
    skipped: int
    dry_run: bool
    results: List[PipelineResult] = field(default_factory=list)


class InstagramContentPipeline:
    """End-to-end Content-to-Publishing Pipeline orchestrating validation, caption generation,
    hashtag generation, sanitization, media verification, and safe publishing decisioning.
    """

    def __init__(
        self,
        image_publisher: Optional[InstagramImagePublisher] = None,
        reel_publisher: Optional[InstagramReelPublisher] = None,
        caption_generator: Optional[InstagramCaptionGenerator] = None,
        dry_run: Optional[bool] = None,
    ):
        config = None
        try:
            config = Config.load_from_env(validate=False)
        except Exception:
            pass

        client = None
        if image_publisher and hasattr(image_publisher, "client"):
            try:
                client = image_publisher.client
            except AttributeError:
                pass
        if not client and reel_publisher and hasattr(reel_publisher, "client"):
            try:
                client = reel_publisher.client
            except AttributeError:
                pass

        token = getattr(client, "access_token", "") if client else ""

        self.image_publisher = image_publisher or InstagramImagePublisher(client=client)
        self.reel_publisher = reel_publisher or InstagramReelPublisher(client=client)
        self.caption_generator = caption_generator or InstagramCaptionGenerator(token=token)

        if dry_run is not None:
            self.dry_run = dry_run
        elif config is not None:
            self.dry_run = config.dry_run
        else:
            self.dry_run = True

        self.logger = logging.getLogger("InstagramContentPipeline")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = RedactingFormatter(
                fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                token=token if isinstance(token, str) else "",
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def process_content(self, content: InstagramContent) -> PipelineResult:
        """Executes the pipeline stages: validation, sanitization, caption/hashtag generation,
        media validation, and publishing (or dry-run execution).
        """
        media_type = (content.media_type or "IMAGE").strip().upper()

        try:
            self.logger.info(f"Pipeline started for category '{content.category}', media_type '{media_type}'")

            if media_type not in ("IMAGE", "REEL"):
                raise InstagramConfigError(f"Unsupported media_type: '{content.media_type}'. Must be 'IMAGE' or 'REEL'.")

            if media_type == "IMAGE" and not content.image_url:
                raise InstagramConfigError("Image content requires a non-empty image_url.")

            if media_type == "REEL" and not content.video_url:
                raise InstagramConfigError("Reel content requires a non-empty video_url.")

            if not content.title and not content.summary and not content.caption:
                raise InstagramConfigError("Content requires a title/summary or explicit caption.")

            sanitized_title = ContentSanitizer.sanitize_content(content.title or "")
            sanitized_summary = ContentSanitizer.sanitize_content(content.summary or "")

            self.logger.info("Content sanitized successfully.")

            if content.caption and content.caption.strip():
                final_caption = ContentSanitizer.sanitize_content(content.caption.strip())
                tags = HashtagGenerator.generate_hashtags(
                    category=content.category,
                    custom_hashtags=content.hashtags,
                )
            else:
                tags = HashtagGenerator.generate_hashtags(
                    category=content.category,
                    custom_hashtags=content.hashtags,
                )
                final_caption = self.caption_generator.generate_caption(
                    title=sanitized_title,
                    summary=sanitized_summary,
                    category=content.category,
                    source=content.source,
                    hashtags=content.hashtags,
                )

            self.logger.info("Caption and hashtags generated successfully.")

            CaptionValidator.validate_caption(final_caption)
            self.logger.info("Caption validated successfully.")

            if media_type == "IMAGE":
                self.image_publisher.validate_image_url(content.image_url)  # type: ignore
                self.logger.info("Image URL validated successfully.")
            elif media_type == "REEL":
                self.reel_publisher.validate_video_url(content.video_url)  # type: ignore
                self.logger.info("Video URL validated successfully.")

            if self.dry_run:
                self.logger.info("DRY_RUN mode enabled. Skipping Instagram API publishing.")
                return PipelineResult(
                    success=True,
                    dry_run=True,
                    media_type=media_type,
                    caption=final_caption,
                    hashtags=tags,
                    creation_id=None,
                    media_id=None,
                    status="SKIPPED",
                    message="Pipeline validation and preparation complete. Publishing skipped (DRY_RUN enabled).",
                )

            self.logger.info(f"Executing real {media_type} publishing...")
            if media_type == "IMAGE":
                pub_res = self.image_publisher.publish_image(
                    image_url=content.image_url,  # type: ignore
                    caption=final_caption,
                )
                return PipelineResult(
                    success=pub_res.success,
                    dry_run=False,
                    media_type="IMAGE",
                    caption=final_caption,
                    hashtags=tags,
                    creation_id=pub_res.creation_id,
                    media_id=pub_res.media_id,
                    status="PUBLISHED" if pub_res.success else "FAILED",
                    message=pub_res.message,
                    error=None if pub_res.success else pub_res.message,
                )
            else:
                pub_res = self.reel_publisher.publish_reel(
                    video_url=content.video_url,  # type: ignore
                    caption=final_caption,
                )
                return PipelineResult(
                    success=pub_res.success,
                    dry_run=False,
                    media_type="REEL",
                    caption=final_caption,
                    hashtags=tags,
                    creation_id=pub_res.creation_id,
                    media_id=pub_res.media_id,
                    status=pub_res.status or ("PUBLISHED" if pub_res.success else "FAILED"),
                    message=pub_res.message,
                    error=None if pub_res.success else pub_res.message,
                )

        except InstagramError as e:
            msg = redact_token(str(e))
            self.logger.error(f"Pipeline processing failed: {msg}")
            return PipelineResult(
                success=False,
                dry_run=self.dry_run,
                media_type=media_type,
                caption="",
                hashtags=[],
                status="FAILED",
                message=msg,
                error=msg,
            )
        except Exception as e:
            msg = redact_token(str(e))
            self.logger.error(f"Unexpected error in pipeline: {msg}")
            return PipelineResult(
                success=False,
                dry_run=self.dry_run,
                media_type=media_type,
                caption="",
                hashtags=[],
                status="FAILED",
                message=f"Unexpected error: {msg}",
                error=msg,
            )

    def process_batch(
        self,
        items: List[Dict[str, Any]],
        normalizer: Optional[InstagramContentNormalizer] = None,
        acquirer: Optional[InstagramMediaAcquirer] = None,
        deduplicator: Optional[InstagramMediaDeduplicator] = None,
    ) -> BatchResult:
        """Processes a list of raw content records independently through normalization, media acquisition,

        deduplication checking, and pipeline execution.
        """
        normalizer = normalizer or InstagramContentNormalizer()
        acquirer = acquirer or InstagramMediaAcquirer()
        deduplicator = deduplicator or InstagramMediaDeduplicator()

        results: List[PipelineResult] = []
        successful_count = 0
        failed_count = 0
        duplicate_count = 0
        skipped_count = 0

        total_items = len(items) if isinstance(items, list) else 0

        if not items or not isinstance(items, list):
            return BatchResult(
                total=0,
                successful=0,
                failed=0,
                duplicates=0,
                skipped=0,
                dry_run=self.dry_run,
                results=[],
            )

        for raw_item in items:
            try:
                # 1. Normalize
                content = normalizer.normalize(raw_item)
                content_id = (content.metadata or {}).get("content_id")
                media_url = content.image_url if content.media_type == "IMAGE" else content.video_url

                # 2. Check Deduplication
                if deduplicator.is_duplicate(content_id=content_id, url=media_url):
                    self.logger.warning(f"Skipping duplicate content ID '{content_id}' (URL: {media_url})")
                    duplicate_count += 1
                    skipped_count += 1
                    res = PipelineResult(
                        success=True,
                        dry_run=self.dry_run,
                        media_type=content.media_type,
                        status="DUPLICATE",
                        message=f"Duplicate content item '{content_id}' skipped.",
                    )
                    results.append(res)
                    continue

                # 3. Media Acquisition & Verification
                if media_url:
                    acquirer.acquire_media(url=media_url, media_type=content.media_type)

                # 4. Pipeline Processing
                res = self.process_content(content)
                results.append(res)

                if res.success:
                    successful_count += 1
                    if res.dry_run:
                        skipped_count += 1
                    # Record in deduplication history
                    deduplicator.mark_processed(content_id=content_id, url=media_url, status=res.status)
                else:
                    failed_count += 1

            except Exception as e:
                failed_count += 1
                msg = redact_token(str(e))
                self.logger.error(f"Error processing batch item: {msg}")
                results.append(
                    PipelineResult(
                        success=False,
                        dry_run=self.dry_run,
                        media_type="UNKNOWN",
                        status="FAILED",
                        message=msg,
                        error=msg,
                    )
                )

        return BatchResult(
            total=total_items,
            successful=successful_count,
            failed=failed_count,
            duplicates=duplicate_count,
            skipped=skipped_count,
            dry_run=self.dry_run,
            results=results,
        )
