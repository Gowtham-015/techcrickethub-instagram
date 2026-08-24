from dataclasses import dataclass
from typing import Any, Dict, List
from instagram_analytics import InstagramAnalyticsEvent


@dataclass
class InstagramMetrics:
    """Aggregated publishing performance metrics and rates."""

    total_discovered: int = 0
    total_accepted: int = 0
    total_rejected: int = 0
    total_queued: int = 0
    total_scheduled: int = 0
    total_published: int = 0
    total_failed: int = 0
    total_skipped: int = 0
    total_duplicates: int = 0
    publish_success_rate: float = 0.0
    failure_rate: float = 0.0
    duplicate_rate: float = 0.0
    rejection_rate: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_discovered": self.total_discovered,
            "total_accepted": self.total_accepted,
            "total_rejected": self.total_rejected,
            "total_queued": self.total_queued,
            "total_scheduled": self.total_scheduled,
            "total_published": self.total_published,
            "total_failed": self.total_failed,
            "total_skipped": self.total_skipped,
            "total_duplicates": self.total_duplicates,
            "publish_success_rate": self.publish_success_rate,
            "failure_rate": self.failure_rate,
            "duplicate_rate": self.duplicate_rate,
            "rejection_rate": self.rejection_rate,
        }

    @classmethod
    def calculate(cls, events: List[InstagramAnalyticsEvent]) -> "InstagramMetrics":
        """Calculates aggregated publishing metrics from event list with safe division."""
        discovered = sum(1 for e in events if e.event_type == "DISCOVERED")
        accepted = sum(1 for e in events if e.event_type == "ACCEPTED")
        rejected = sum(1 for e in events if e.event_type == "REJECTED")
        queued = sum(1 for e in events if e.event_type == "QUEUED")
        scheduled = sum(1 for e in events if e.event_type == "SCHEDULED")
        published = sum(1 for e in events if e.event_type == "PUBLISHED")
        failed = sum(1 for e in events if e.event_type == "FAILED")
        skipped = sum(1 for e in events if e.event_type == "SKIPPED")
        duplicates = sum(1 for e in events if e.event_type == "DUPLICATE")

        # Publish success rate: published / (published + failed)
        pub_attempts = published + failed
        success_rate = round((published / pub_attempts) * 100.0, 2) if pub_attempts > 0 else 0.0
        fail_rate = round((failed / pub_attempts) * 100.0, 2) if pub_attempts > 0 else 0.0

        # Duplicate & Rejection rates relative to discovered items
        dup_rate = round((duplicates / discovered) * 100.0, 2) if discovered > 0 else 0.0
        rej_rate = round((rejected / discovered) * 100.0, 2) if discovered > 0 else 0.0

        return cls(
            total_discovered=discovered,
            total_accepted=accepted,
            total_rejected=rejected,
            total_queued=queued,
            total_scheduled=scheduled,
            total_published=published,
            total_failed=failed,
            total_skipped=skipped,
            total_duplicates=duplicates,
            publish_success_rate=success_rate,
            failure_rate=fail_rate,
            duplicate_rate=dup_rate,
            rejection_rate=rej_rate,
        )
