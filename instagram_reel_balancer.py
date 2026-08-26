import math
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from config import Config

logger = logging.getLogger("InstagramReelBalancer")


@dataclass
class ReelBalanceMetrics:
    total_items: int
    reel_count: int
    image_count: int
    reel_percentage: float
    target_percentage: float
    min_reels_required: int
    max_images_allowed: int
    status: str  # BALANCED, REEL_DEFICIT
    priority_boost_active: bool
    reel_deficit: bool = False
    should_prefer_reels: bool = False


class InstagramReelBalancer:
    """Enforces Reel-first policy (minimum 80% Reels / maximum 20% Images) over rolling 30-item window."""

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config.load_from_env(validate=False)
        self.target_pct = getattr(self.config, "reel_target_percent", 80)  # 80%
        self.window_size = getattr(self.config, "rolling_window_size", 30)  # 30

    def calculate_targets(self, window: Optional[int] = None) -> Dict[str, int]:
        """Calculates exact minimum Reels and maximum Images for a window size."""
        w = window or self.window_size
        min_reels = math.ceil(w * (self.target_pct / 100.0))  # ceil(30 * 0.80) = 24
        max_images = w - min_reels  # 30 - 24 = 6
        return {
            "window_size": w,
            "min_reels": min_reels,
            "max_images": max_images,
            "target_pct": self.target_pct,
        }

    def evaluate_balance(self, items: List[Dict[str, Any]]) -> ReelBalanceMetrics:
        """Evaluates rolling window items and returns Reel balance metrics."""
        targets = self.calculate_targets()
        recent_items = items[-self.window_size :] if items else []
        total = len(recent_items)

        def _get_mtype(it: Any) -> str:
            if isinstance(it, dict):
                return str(it.get("media_type", "")).upper()
            return str(getattr(it, "media_type", "")).upper()

        reel_count = sum(1 for item in recent_items if _get_mtype(item) == "REEL")
        image_count = total - reel_count

        pct = (reel_count / total * 100.0) if total > 0 else 80.0
        reel_deficit = pct < self.target_pct if total > 0 else False
        image_overflow = image_count > targets["max_images"] if total >= 5 else False

        status = "REEL_DEFICIT" if reel_deficit else "BALANCED"
        prefer_reels = reel_deficit or image_overflow or (pct < self.target_pct)

        logger.info(
            f"ReelBalancer evaluation: Window={total}/{self.window_size}, "
            f"Reels={reel_count} ({round(pct, 1)}%), Images={image_count}, Target={self.target_pct}%, Status={status}"
        )

        return ReelBalanceMetrics(
            total_items=total,
            reel_count=reel_count,
            image_count=image_count,
            reel_percentage=round(pct, 1),
            target_percentage=float(self.target_pct),
            min_reels_required=targets["min_reels"],
            max_images_allowed=targets["max_images"],
            status=status,
            priority_boost_active=reel_deficit,
            reel_deficit=reel_deficit,
            should_prefer_reels=prefer_reels,
        )
