from collections import Counter
from typing import Any, Dict, List, Optional
from instagram_queue import InstagramQueueItem


class InstagramCategoryBalancer:
    """Monitors category distribution in the queue to prevent category flooding and promote diversity."""

    def __init__(self, max_category_percentage: float = 40.0, window_size: int = 10):
        self.max_category_percentage = max_category_percentage
        self.window_size = window_size

    def calculate_distribution(self, queue_items: List[InstagramQueueItem]) -> Dict[str, float]:
        """Calculates category distribution percentages over the recent window size."""
        if not queue_items:
            return {}

        recent_items = queue_items[-self.window_size:] if len(queue_items) > self.window_size else queue_items
        total = len(recent_items)
        if total == 0:
            return {}

        counts = Counter(item.category.lower() for item in recent_items if item.category)
        return {cat: round((count / total) * 100.0, 1) for cat, count in counts.items()}

    def is_category_overrepresented(self, category: str, queue_items: List[InstagramQueueItem]) -> bool:
        """Determines if a category exceeds the maximum configured percentage in the recent window."""
        if not category or not queue_items:
            return False

        dist = self.calculate_distribution(queue_items)
        cat_clean = category.lower()
        return dist.get(cat_clean, 0.0) >= self.max_category_percentage

    def get_balance_status(self, queue_items: List[InstagramQueueItem]) -> Dict[str, Any]:
        """Returns overall category balance report."""
        dist = self.calculate_distribution(queue_items)
        overrepresented = [
            cat for cat, pct in dist.items() if pct >= self.max_category_percentage
        ]
        status = "OVERREPRESENTED" if overrepresented else "BALANCED"
        return {
            "distribution": dist,
            "overrepresented_categories": overrepresented,
            "status": status,
            "window_size": self.window_size,
            "max_percentage_threshold": self.max_category_percentage,
        }
