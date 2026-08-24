from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from config import Config
from instagram_category_balancer import InstagramCategoryBalancer
from instagram_content_priority import InstagramContentPriority
from instagram_content_scorer import ContentScore, InstagramContentScorer
from instagram_pipeline import InstagramContent
from instagram_queue import InstagramQueueItem
from instagram_scheduler import InstagramScheduler


class InstagramSmartScheduler:
    """Smart scheduling layer on top of InstagramScheduler enforcing posting windows (morning, afternoon, evening),

    Asia/Kolkata timezone calculations, category balance, media-type balance, and content score ranking.
    """

    def __init__(
        self,
        config: Optional[Config] = None,
        scheduler: Optional[InstagramScheduler] = None,
    ):
        self.config = config or Config.load_from_env(validate=False)
        self.scheduler = scheduler or InstagramScheduler(config=self.config)
        self.scorer = InstagramContentScorer(score_threshold=self.config.content_score_threshold)
        self.priority = InstagramContentPriority(min_score_threshold=self.config.content_score_threshold)
        self.balancer = InstagramCategoryBalancer(
            max_category_percentage=self.config.max_category_percentage,
            window_size=self.config.category_window_size,
        )

        try:
            self.tz = ZoneInfo(self.config.timezone)
        except Exception:
            self.tz = timezone.utc

    def parse_time(self, time_str: str) -> tuple[int, int]:
        """Parses 'HH:MM' string into (hour, minute)."""
        try:
            parts = time_str.split(":")
            return int(parts[0]), int(parts[1])
        except Exception:
            return 8, 0

    def get_posting_windows(self) -> List[tuple[tuple[int, int], tuple[int, int]]]:
        """Returns list of configured posting windows ((start_h, start_m), (end_h, end_m))."""
        m_start = self.parse_time(self.config.morning_start)
        m_end = self.parse_time(self.config.morning_end)

        a_start = self.parse_time(self.config.afternoon_start)
        a_end = self.parse_time(self.config.afternoon_end)

        e_start = self.parse_time(self.config.evening_start)
        e_end = self.parse_time(self.config.evening_end)

        return [(m_start, m_end), (a_start, a_end), (e_start, e_end)]

    def is_within_posting_window(self, dt: datetime) -> bool:
        """Determines if a given local datetime falls within one of the defined posting windows."""
        dt_local = dt.astimezone(self.tz)
        t_minutes = dt_local.hour * 60 + dt_local.minute

        for (sh, sm), (eh, em) in self.get_posting_windows():
            start_m = sh * 60 + sm
            end_m = eh * 60 + em
            if start_m <= t_minutes <= end_m:
                return True

        return False

    def calculate_next_slot(
        self,
        queue_items: List[InstagramQueueItem],
        media_type: str = "IMAGE",
        now_dt: Optional[datetime] = None,
    ) -> datetime:
        """Calculates the optimal future scheduled timestamp in Asia/Kolkata timezone

        respecting minimum interval, posting windows, and media-type balance.
        """
        now = now_dt or datetime.now(self.tz)
        if now.tzinfo is None:
            now = now.replace(tzinfo=self.tz)

        min_interval = timedelta(minutes=self.config.min_post_interval_minutes)
        earliest = now + min_interval

        # Check last scheduled item timestamp
        if queue_items:
            active_items = [
                i for i in queue_items if i.status in ("PENDING", "SCHEDULED", "PROCESSING")
            ]
            if active_items:
                last_item = active_items[-1]
                try:
                    last_dt = datetime.fromisoformat(last_item.scheduled_at.replace("Z", "+00:00")).astimezone(self.tz)
                    if last_dt + min_interval > earliest:
                        earliest = last_dt + min_interval
                except Exception:
                    pass

        # Find next valid posting window starting from earliest
        candidate = earliest
        for _ in range(1440):  # Check minute by minute up to 24 hours
            if self.is_within_posting_window(candidate):
                return candidate.astimezone(timezone.utc)
            candidate += timedelta(minutes=10)

        return earliest.astimezone(timezone.utc)

    def rank_candidates(
        self,
        contents: List[InstagramContent],
        queue_items: List[InstagramQueueItem],
    ) -> List[tuple[InstagramContent, ContentScore]]:
        """Ranks candidate items based on content score, priority weight, and category balancing."""
        ranked: List[tuple[InstagramContent, ContentScore, int]] = []

        for content in contents:
            score_obj = self.scorer.score_content(content)
            if score_obj.decision == "REJECT":
                continue

            weight = self.priority.get_weight(score_obj.priority_label)

            # Penalize overrepresented categories
            if self.balancer.is_category_overrepresented(content.category, queue_items):
                weight -= 1.5

            ranked.append((content, score_obj, weight))

        # Sort descending by weight, then total_score
        ranked.sort(key=lambda x: (x[2], x[1].total_score), reverse=True)
        return [(item[0], item[1]) for item in ranked]
