from typing import Dict


class InstagramContentPriority:
    """Manages deterministic priority thresholds and queue admittance decisions for Instagram content."""

    LEVELS: Dict[str, tuple[int, int]] = {
        "CRITICAL": (90, 100),
        "HIGH": (75, 89),
        "NORMAL": (55, 74),
        "LOW": (35, 54),
        "REJECT": (0, 34),
    }

    WEIGHTS: Dict[str, int] = {
        "CRITICAL": 5,
        "HIGH": 4,
        "NORMAL": 3,
        "LOW": 2,
        "REJECT": 1,
    }

    def __init__(self, min_score_threshold: int = 35):
        self.min_score_threshold = min_score_threshold

    def classify(self, score: int) -> str:
        """Returns priority classification label for a score from 0 to 100."""
        score_clean = max(0, min(100, int(score)))

        for level, (low, high) in self.LEVELS.items():
            if low <= score_clean <= high:
                return level
        return "REJECT"

    def should_queue(self, score: int) -> bool:
        """Determines if content is admissible to the Instagram queue."""
        label = self.classify(score)
        return score >= self.min_score_threshold and label != "REJECT"

    def get_weight(self, priority_label: str) -> int:
        """Returns numerical sorting weight for a priority label."""
        return self.WEIGHTS.get(priority_label.upper(), 1)
