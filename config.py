import os
import re
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv
from exceptions import InstagramConfigError


@dataclass
class Config:
    user_id: str
    access_token: str
    api_version: str = "v26.0"
    timeout_seconds: float = 30.0
    log_level: str = "INFO"
    test_image_url: str = ""
    test_reel_video_url: str = ""
    dry_run: bool = True
    scheduler_enabled: bool = False
    timezone: str = "Asia/Kolkata"
    post_interval_minutes: int = 30
    max_queue_size: int = 50
    max_retries: int = 3
    automation_enabled: bool = False
    loop_interval_seconds: int = 60
    heartbeat_interval_seconds: int = 300
    max_items_per_cycle: int = 10
    content_score_threshold: int = 35
    max_category_percentage: float = 40.0
    category_window_size: int = 10
    max_consecutive_reels: int = 2
    max_consecutive_images: int = 3
    min_post_interval_minutes: int = 30
    morning_start: str = "08:00"
    morning_end: str = "10:00"
    afternoon_start: str = "13:00"
    afternoon_end: str = "15:00"
    evening_start: str = "18:00"
    evening_end: str = "21:00"
    analytics_enabled: bool = True
    analytics_min_sample_size: int = 10
    analytics_retention_days: int = 90
    optimization_enabled: bool = True
    analytics_timezone: str = "Asia/Kolkata"

    @classmethod
    def load_from_env(cls, env_path: Optional[str] = None, validate: bool = True) -> "Config":
        """Loads configuration from environment variables and optional .env file."""
        if env_path is not None:
            if env_path != "":
                load_dotenv(dotenv_path=env_path, override=True)
        else:
            load_dotenv(override=True)

        user_id = os.getenv("INSTAGRAM_USER_ID", "").strip()
        access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip()
        api_version = os.getenv("INSTAGRAM_API_VERSION", "v26.0").strip()
        timeout_str = os.getenv("INSTAGRAM_TIMEOUT_SECONDS", "30").strip()
        log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
        test_image_url = os.getenv("INSTAGRAM_TEST_IMAGE_URL", "").strip()
        test_reel_video_url = os.getenv(
            "TEST_REEL_VIDEO_URL",
            os.getenv("INSTAGRAM_TEST_REEL_VIDEO_URL", ""),
        ).strip()
        dry_run_str = os.getenv("INSTAGRAM_DRY_RUN", "true").strip().lower()
        dry_run = dry_run_str not in ("false", "0", "no", "off")

        scheduler_enabled_str = os.getenv("INSTAGRAM_SCHEDULER_ENABLED", "false").strip().lower()
        scheduler_enabled = scheduler_enabled_str in ("true", "1", "yes", "on")

        timezone = os.getenv("INSTAGRAM_TIMEZONE", "Asia/Kolkata").strip()

        interval_str = os.getenv("INSTAGRAM_POST_INTERVAL_MINUTES", "30").strip()
        try:
            post_interval_minutes = int(interval_str)
        except ValueError:
            post_interval_minutes = 30

        queue_size_str = os.getenv("INSTAGRAM_MAX_QUEUE_SIZE", "50").strip()
        try:
            max_queue_size = int(queue_size_str)
        except ValueError:
            max_queue_size = 50

        retries_str = os.getenv("INSTAGRAM_MAX_RETRIES", "3").strip()
        try:
            max_retries = int(retries_str)
        except ValueError:
            max_retries = 3

        automation_enabled_str = os.getenv("INSTAGRAM_AUTOMATION_ENABLED", "false").strip().lower()
        automation_enabled = automation_enabled_str in ("true", "1", "yes", "on")

        loop_interval_str = os.getenv("INSTAGRAM_LOOP_INTERVAL_SECONDS", "60").strip()
        try:
            loop_interval_seconds = int(loop_interval_str)
        except ValueError:
            loop_interval_seconds = 60

        heartbeat_str = os.getenv("INSTAGRAM_HEARTBEAT_INTERVAL_SECONDS", "300").strip()
        try:
            heartbeat_interval_seconds = int(heartbeat_str)
        except ValueError:
            heartbeat_interval_seconds = 300

        max_items_str = os.getenv("INSTAGRAM_MAX_ITEMS_PER_CYCLE", "10").strip()
        try:
            max_items_per_cycle = int(max_items_str)
        except ValueError:
            max_items_per_cycle = 10

        score_thresh_str = os.getenv("INSTAGRAM_CONTENT_SCORE_THRESHOLD", "35").strip()
        try:
            content_score_threshold = int(score_thresh_str)
        except ValueError:
            content_score_threshold = 35

        max_cat_pct_str = os.getenv("INSTAGRAM_MAX_CATEGORY_PERCENTAGE", "40.0").strip()
        try:
            max_category_percentage = float(max_cat_pct_str)
        except ValueError:
            max_category_percentage = 40.0

        cat_window_str = os.getenv("INSTAGRAM_CATEGORY_WINDOW_SIZE", "10").strip()
        try:
            category_window_size = int(cat_window_str)
        except ValueError:
            category_window_size = 10

        max_reels_str = os.getenv("INSTAGRAM_MAX_CONSECUTIVE_REELS", "2").strip()
        try:
            max_consecutive_reels = int(max_reels_str)
        except ValueError:
            max_consecutive_reels = 2

        max_imgs_str = os.getenv("INSTAGRAM_MAX_CONSECUTIVE_IMAGES", "3").strip()
        try:
            max_consecutive_images = int(max_imgs_str)
        except ValueError:
            max_consecutive_images = 3

        min_post_int_str = os.getenv("INSTAGRAM_MIN_POST_INTERVAL_MINUTES", "30").strip()
        try:
            min_post_interval_minutes = int(min_post_int_str)
        except ValueError:
            min_post_interval_minutes = 30

        morning_start = os.getenv("INSTAGRAM_MORNING_START", "08:00").strip()
        morning_end = os.getenv("INSTAGRAM_MORNING_END", "10:00").strip()
        afternoon_start = os.getenv("INSTAGRAM_AFTERNOON_START", "13:00").strip()
        afternoon_end = os.getenv("INSTAGRAM_AFTERNOON_END", "15:00").strip()
        evening_start = os.getenv("INSTAGRAM_EVENING_START", "18:00").strip()
        evening_end = os.getenv("INSTAGRAM_EVENING_END", "21:00").strip()

        analytics_enabled_str = os.getenv("INSTAGRAM_ANALYTICS_ENABLED", "true").strip().lower()
        analytics_enabled = analytics_enabled_str not in ("false", "0", "no", "off")

        sample_size_str = os.getenv("INSTAGRAM_ANALYTICS_MIN_SAMPLE_SIZE", "10").strip()
        try:
            analytics_min_sample_size = int(sample_size_str)
        except ValueError:
            analytics_min_sample_size = 10

        retention_days_str = os.getenv("INSTAGRAM_ANALYTICS_RETENTION_DAYS", "90").strip()
        try:
            analytics_retention_days = int(retention_days_str)
        except ValueError:
            analytics_retention_days = 90

        optimization_enabled_str = os.getenv("INSTAGRAM_OPTIMIZATION_ENABLED", "true").strip().lower()
        optimization_enabled = optimization_enabled_str not in ("false", "0", "no", "off")

        analytics_timezone = os.getenv("INSTAGRAM_ANALYTICS_TIMEZONE", "Asia/Kolkata").strip()

        try:
            timeout_seconds = float(timeout_str)
        except ValueError:
            raise InstagramConfigError(
                f"Invalid INSTAGRAM_TIMEOUT_SECONDS value: '{timeout_str}'. Must be a positive number."
            )

        config = cls(
            user_id=user_id,
            access_token=access_token,
            api_version=api_version,
            timeout_seconds=timeout_seconds,
            log_level=log_level,
            test_image_url=test_image_url,
            test_reel_video_url=test_reel_video_url,
            dry_run=dry_run,
            scheduler_enabled=scheduler_enabled,
            timezone=timezone,
            post_interval_minutes=post_interval_minutes,
            max_queue_size=max_queue_size,
            max_retries=max_retries,
            automation_enabled=automation_enabled,
            loop_interval_seconds=loop_interval_seconds,
            heartbeat_interval_seconds=heartbeat_interval_seconds,
            max_items_per_cycle=max_items_per_cycle,
            content_score_threshold=content_score_threshold,
            max_category_percentage=max_category_percentage,
            category_window_size=category_window_size,
            max_consecutive_reels=max_consecutive_reels,
            max_consecutive_images=max_consecutive_images,
            min_post_interval_minutes=min_post_interval_minutes,
            morning_start=morning_start,
            morning_end=morning_end,
            afternoon_start=afternoon_start,
            afternoon_end=afternoon_end,
            evening_start=evening_start,
            evening_end=evening_end,
            analytics_enabled=analytics_enabled,
            analytics_min_sample_size=analytics_min_sample_size,
            analytics_retention_days=analytics_retention_days,
            optimization_enabled=optimization_enabled,
            analytics_timezone=analytics_timezone,
        )

        if validate:
            config.validate()

        return config

    def validate(self) -> None:
        """Validates configuration parameters."""
        if not self.user_id:
            raise InstagramConfigError("INSTAGRAM_USER_ID is required and cannot be empty.")

        if not self.access_token or self.access_token == "YOUR_ACCESS_TOKEN_HERE":
            raise InstagramConfigError(
                "INSTAGRAM_ACCESS_TOKEN is missing or set to placeholder value. "
                "Please configure a valid access token in .env."
            )

        if self.timeout_seconds <= 0:
            raise InstagramConfigError(
                f"INSTAGRAM_TIMEOUT_SECONDS must be > 0, got {self.timeout_seconds}."
            )

        if not re.match(r"^v\d+\.\d+$", self.api_version):
            raise InstagramConfigError(
                f"Invalid INSTAGRAM_API_VERSION format: '{self.api_version}'. "
                "Expected format 'vXX.X' (e.g., 'v26.0')."
            )

    def __repr__(self) -> str:
        safe_token = "[REDACTED]" if self.access_token else "NOT_SET"
        return (
            f"Config(user_id={self.user_id!r}, access_token={safe_token!r}, "
            f"api_version={self.api_version!r}, timeout_seconds={self.timeout_seconds}, "
            f"log_level={self.log_level!r}, dry_run={self.dry_run}, "
            f"analytics_enabled={self.analytics_enabled}, "
            f"analytics_min_sample_size={self.analytics_min_sample_size})"
        )

    def __str__(self) -> str:
        return self.__repr__()
