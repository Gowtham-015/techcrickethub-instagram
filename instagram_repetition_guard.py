import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional
from instagram_pipeline import InstagramContent
from instagram_queue import InstagramQueueItem


@dataclass
class RepetitionCheckResult:
    """Represents outcome of repetition analysis."""

    is_repeated: bool
    repetition_type: str  # EXACT_DUPLICATE, NEAR_DUPLICATE, SIMILAR_CONTENT, NONE
    similarity_score: float
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_repeated": self.is_repeated,
            "repetition_type": self.repetition_type,
            "similarity_score": self.similarity_score,
            "reason": self.reason,
        }


class InstagramRepetitionGuard:
    """Detects exact duplicates, near duplicates, repeated summaries, and media URL repeats."""

    def __init__(self, near_duplicate_threshold: float = 0.85, similarity_threshold: float = 0.70):
        self.near_duplicate_threshold = near_duplicate_threshold
        self.similarity_threshold = similarity_threshold

    def normalize_string(self, text: str) -> str:
        """Normalizes text for string comparison."""
        if not text:
            return ""
        s = text.lower()
        s = re.sub(r"[^\w\s]", "", s)
        return " ".join(s.split())

    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculates SequenceMatcher similarity ratio (0.0 to 1.0)."""
        n1 = self.normalize_string(text1)
        n2 = self.normalize_string(text2)
        if not n1 or not n2:
            return 0.0
        if n1 == n2:
            return 1.0
        return round(SequenceMatcher(None, n1, n2).ratio(), 3)

    def check_repetition(
        self,
        content: InstagramContent,
        existing_items: List[InstagramQueueItem],
    ) -> RepetitionCheckResult:
        """Compares content against existing items for exact or near duplicates."""
        if not existing_items:
            return RepetitionCheckResult(
                is_repeated=False,
                repetition_type="NONE",
                similarity_score=0.0,
                reason="No existing queue items for comparison.",
            )

        new_title = content.title or ""
        new_url = content.image_url if content.media_type == "IMAGE" else content.video_url
        new_content_id = (content.metadata or {}).get("content_id")

        for item in existing_items:
            # 1. Exact media_url match
            if new_url and item.media_url and new_url.strip() == item.media_url.strip() and "maxresdefault.jpg" not in new_url:
                return RepetitionCheckResult(
                    is_repeated=True,
                    repetition_type="EXACT_DUPLICATE",
                    similarity_score=1.0,
                    reason=f"Exact media URL match with queue_id '{item.queue_id}'.",
                )

            # 2. Exact content_id match
            if new_content_id and item.content_id and new_content_id == item.content_id:
                return RepetitionCheckResult(
                    is_repeated=True,
                    repetition_type="EXACT_DUPLICATE",
                    similarity_score=1.0,
                    reason=f"Exact content_id match with queue_id '{item.queue_id}'.",
                )

            # 3. Title similarity comparison
            sim = self.calculate_similarity(new_title, item.title or "")
            if sim >= 0.99:
                return RepetitionCheckResult(
                    is_repeated=True,
                    repetition_type="EXACT_DUPLICATE",
                    similarity_score=sim,
                    reason=f"Exact title match with queue_id '{item.queue_id}'.",
                )
            elif sim >= self.near_duplicate_threshold:
                return RepetitionCheckResult(
                    is_repeated=True,
                    repetition_type="NEAR_DUPLICATE",
                    similarity_score=sim,
                    reason=f"Near-duplicate title detected (similarity {sim}) with queue_id '{item.queue_id}'.",
                )
            elif sim >= self.similarity_threshold:
                return RepetitionCheckResult(
                    is_repeated=True,
                    repetition_type="NEAR_DUPLICATE",
                    similarity_score=sim,
                    reason=f"Similar title detected (similarity {sim}) with queue_id '{item.queue_id}'.",
                )

        return RepetitionCheckResult(
            is_repeated=False,
            repetition_type="NONE",
            similarity_score=0.0,
            reason="Content is fresh and non-repetitive.",
        )
