import math
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from config import Config

logger = logging.getLogger("InstagramCricketBalancer")


@dataclass
class BalanceMetrics:
    total_items: int
    cricket_count: int
    non_cricket_count: int
    cricket_percentage: float
    target_percentage: float
    min_cricket_required: int
    max_non_cricket_allowed: int
    status: str  # BALANCED, CRICKET_DEFICIT
    priority_boost_active: bool


class InstagramCricketBalancer:
    """Enforces 75% minimum Cricket target distribution over rolling 30-item window."""

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config.load_from_env(validate=False)
        self.target_pct = self.config.cricket_target_percent  # 75%
        self.window_size = self.config.rolling_window_size  # 30

    def calculate_targets(self, window: Optional[int] = None) -> Dict[str, int]:
        """Calculates exact minimum cricket and maximum non-cricket items for a window size."""
        w = window or self.window_size
        min_cricket = math.ceil(w * (self.target_pct / 100.0))  # ceil(30 * 0.75) = 23
        max_non_cricket = w - min_cricket  # 30 - 23 = 7
        return {
            "window_size": w,
            "min_cricket": min_cricket,
            "max_non_cricket": max_non_cricket,
            "target_pct": self.target_pct,
        }

    def evaluate_balance(self, items: List[Dict[str, Any]]) -> BalanceMetrics:
        """Evaluates rolling window items and returns balance metrics."""
        targets = self.calculate_targets()
        recent_items = items[-self.window_size :] if items else []
        total = len(recent_items)

        cricket_count = sum(
            1 for item in recent_items if str(item.get("category", "")).lower() == "cricket"
        )
        non_cricket_count = total - cricket_count

        pct = (cricket_count / total * 100.0) if total > 0 else 100.0
        deficit = pct < self.target_pct if total > 0 else False

        status = "CRICKET_DEFICIT" if deficit else "BALANCED"

        logger.info(
            f"CricketBalancer evaluation: Window={total}/{self.window_size}, "
            f"Cricket={cricket_count} ({round(pct, 1)}%), Target={self.target_pct}%, Status={status}"
        )

        return BalanceMetrics(
            total_items=total,
            cricket_count=cricket_count,
            non_cricket_count=non_cricket_count,
            cricket_percentage=round(pct, 1),
            target_percentage=float(self.target_pct),
            min_cricket_required=targets["min_cricket"],
            max_non_cricket_allowed=targets["max_non_cricket"],
            status=status,
            priority_boost_active=deficit,
        )
