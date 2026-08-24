import re
from typing import Dict, List, Optional, Tuple


class InstagramCategoryIntelligence:
    """Keyword-based category detection engine with text normalization and confidence scoring."""

    CATEGORY_KEYWORDS: Dict[str, List[str]] = {
        "cricket": [
            "cricket",
            "ipl",
            "bcci",
            "icc",
            "wicket",
            "runs",
            "batsman",
            "bowler",
            "test match",
            "t20",
            "odi",
            "rohit",
            "kohli",
            "dhoni",
            "match",
            "tournament",
            "bilateral",
        ],
        "ai": [
            "ai",
            "artificial intelligence",
            "machine learning",
            "deep learning",
            "llm",
            "neural",
            "chatgpt",
            "openai",
            "copilot",
            "generative ai",
            "model",
        ],
        "technology": [
            "tech",
            "technology",
            "software",
            "hardware",
            "app",
            "mobile",
            "gadget",
            "cloud",
            "developer",
            "code",
            "operating system",
            "cybersecurity",
            "architecture",
        ],
        "sports": [
            "sports",
            "football",
            "soccer",
            "tennis",
            "basketball",
            "olympics",
            "athlete",
            "championship",
            "game",
            "league",
        ],
        "entertainment": [
            "entertainment",
            "movie",
            "film",
            "cinema",
            "actor",
            "actress",
            "hollywood",
            "bollywood",
            "teaser",
            "trailer",
            "box office",
            "show",
        ],
    }

    def __init__(self, min_confidence: float = 0.3):
        self.min_confidence = min_confidence

    def normalize_text(self, text: str) -> str:
        """Normalizes text for keyword matching."""
        if not text:
            return ""
        text_clean = text.lower()
        text_clean = re.sub(r"[^\w\s]", " ", text_clean)
        return " ".join(text_clean.split())

    def detect_category(
        self,
        title: str,
        summary: str = "",
        default_category: Optional[str] = None,
    ) -> Tuple[str, float]:
        """Detects best matching category and calculates confidence score (0.0 to 1.0)."""
        combined = self.normalize_text(f"{title} {summary}")
        if not combined:
            fallback = default_category.lower() if default_category else "unknown"
            return fallback, 0.0

        scores: Dict[str, int] = {cat: 0 for cat in self.CATEGORY_KEYWORDS}

        for cat, keywords in self.CATEGORY_KEYWORDS.items():
            for kw in keywords:
                # Word boundary match
                pattern = r"\b" + re.escape(kw) + r"\b"
                matches = len(re.findall(pattern, combined))
                if matches > 0:
                    # Give higher weight if keyword matched in title area
                    scores[cat] += matches * 2

        max_score = max(scores.values()) if scores else 0
        total_score = sum(scores.values())

        if max_score == 0 or total_score == 0:
            fallback = default_category.lower() if default_category else "unknown"
            return fallback, 0.0

        best_category = max(scores, key=scores.get)  # type: ignore
        confidence = round(max_score / float(total_score), 2)

        if confidence < self.min_confidence:
            fallback = default_category.lower() if default_category else "unknown"
            return fallback, confidence

        return best_category, confidence
