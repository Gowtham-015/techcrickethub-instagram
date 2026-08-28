import re
from typing import List, Optional
from exceptions import InstagramConfigError, InstagramError
from security import redact_token


CATEGORY_EMOJIS = {
    "cricket": "🔥",
    "sports": "🏆",
    "technology": "🚀",
    "entertainment": "🎬",
    "geopolitics": "🌐",
    "democracy": "🏛️",
    "general news": "📰",
}

DEFAULT_CATEGORY_HASHTAGS = {
    "cricket": ["#Cricket", "#CricketNews", "#SportsNews", "#IndianCricket", "#MatchUpdate"],
    "sports": ["#Sports", "#SportsNews", "#GameDay", "#Athletes", "#SportsUpdate"],
    "technology": ["#Technology", "#TechNews", "#AI", "#Innovation", "#TechUpdate"],
    "entertainment": ["#Entertainment", "#MovieNews", "#Trending", "#PopCulture"],
    "geopolitics": ["#Geopolitics", "#WorldNews", "#GlobalAffairs", "#Diplomacy", "#InternationalNews"],
    "democracy": ["#Democracy", "#Governance", "#PublicPolicy", "#Elections", "#CivicUpdate"],
    "general news": ["#News", "#BreakingNews", "#LatestNews", "#DailyNews", "#NewsUpdate"],
}



class HashtagGenerator:
    """Utility for generating, normalizing, and deduplicating category-based Instagram hashtags."""

    MANDATORY_HASHTAG = "#TechCricketHub"

    @classmethod
    def normalize_hashtag(cls, tag: str) -> str:
        """Normalizes a single hashtag string."""
        if not tag or not isinstance(tag, str):
            return ""
        clean = tag.strip()
        if not clean.startswith("#"):
            clean = f"#{clean}"
        clean_tag = "#" + re.sub(r"[^\w]", "", clean[1:])
        return clean_tag if len(clean_tag) > 1 else ""

    @classmethod
    def generate_hashtags(
        cls,
        category: str = "cricket",
        custom_hashtags: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[str]:
        """Generates a list of normalized, deduplicated hashtags for a given category."""
        category_clean = (category or "cricket").strip().lower()
        limit = min(max(1, limit), 30)

        raw_tags = [cls.MANDATORY_HASHTAG]

        category_tags = DEFAULT_CATEGORY_HASHTAGS.get(category_clean, DEFAULT_CATEGORY_HASHTAGS["general news"])
        raw_tags.extend(category_tags)

        if custom_hashtags and isinstance(custom_hashtags, list):
            raw_tags.extend(custom_hashtags)

        seen = set()
        final_tags = []
        for tag in raw_tags:
            norm = cls.normalize_hashtag(tag)
            if norm and norm.lower() not in seen:
                seen.add(norm.lower())
                final_tags.append(norm)
                if len(final_tags) >= limit:
                    break

        return final_tags


class ContentSanitizer:
    """Utility for sanitizing content text, stripping tokens/secrets, and normalizing whitespace."""

    @classmethod
    def sanitize_content(cls, text: str, token: Optional[str] = None) -> str:
        """Sanitizes text by scrubbing tokens/secrets, control characters, and excess whitespace."""
        if not text or not isinstance(text, str):
            return ""

        sanitized = redact_token(text, token=token)

        # Remove non-printable control characters (preserve \n, \r, \t)
        sanitized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", sanitized)

        # Normalize newlines (max 2 consecutive blank lines)
        sanitized = re.sub(r"\n{3,}", "\n\n", sanitized)

        lines = [line.strip() for line in sanitized.splitlines()]
        sanitized = "\n".join(lines).strip()

        return sanitized


class CaptionValidator:
    """Validator ensuring Instagram caption length, hashtag count, and security compliance."""

    MAX_CAPTION_LENGTH = 2200
    MAX_HASHTAG_LIMIT = 30

    @classmethod
    def validate_caption(cls, caption: str, token: Optional[str] = None) -> None:
        """Validates caption string against Instagram constraints and security rules."""
        if not caption or not isinstance(caption, str) or not caption.strip():
            raise InstagramError("Caption cannot be empty.", token=token)

        if len(caption) > cls.MAX_CAPTION_LENGTH:
            raise InstagramError(
                f"Caption exceeds Instagram's limit of {cls.MAX_CAPTION_LENGTH} characters "
                f"(got {len(caption)} characters).",
                token=token,
            )

        hashtags = re.findall(r"#\w+", caption)
        if len(hashtags) > cls.MAX_HASHTAG_LIMIT:
            raise InstagramError(
                f"Caption exceeds maximum limit of {cls.MAX_HASHTAG_LIMIT} hashtags "
                f"(got {len(hashtags)} hashtags).",
                token=token,
            )

        if "access_token=" in caption.lower():
            raise InstagramError(
                "Security Violation: Caption contains unredacted access_token parameter.",
                token=token,
            )

        if token and token in caption:
            raise InstagramError(
                "Security Violation: Caption contains unredacted secret token.",
                token=token,
            )

        lower_hashtags = [h.lower() for h in hashtags]
        if len(lower_hashtags) != len(set(lower_hashtags)):
            duplicates = [h for h in set(lower_hashtags) if lower_hashtags.count(h) > 1]
            raise InstagramError(
                f"Caption contains duplicate hashtags: {', '.join(duplicates)}",
                token=token,
            )

        words = re.findall(r"\b\w{4,}\b", caption.lower())
        for w in set(words):
            if words.count(w) > 10 and not w.startswith("#"):
                raise InstagramError(
                    f"Caption contains excessive repeated word spam: '{w}'.",
                    token=token,
                )


class InstagramCaptionGenerator:
    """Service for generating structured, sanitized, and validated Instagram captions."""

    def __init__(self, token: Optional[str] = None):
        self.token = token

    def generate_caption(
        self,
        title: str,
        summary: str,
        category: str = "cricket",
        source: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        hashtags: Optional[List[str]] = None,
        max_hashtags: int = 10,
    ) -> str:
        """Generates a complete, structured, and validated Instagram caption."""
        category_clean = (category or "cricket").strip().lower()

        clean_title = ContentSanitizer.sanitize_content(title or "", token=self.token)
        clean_summary = ContentSanitizer.sanitize_content(summary or "", token=self.token)

        if not clean_title and not clean_summary:
            raise InstagramConfigError("Cannot generate caption: both title and summary are empty.", token=self.token)

        emoji_hook = CATEGORY_EMOJIS.get(category_clean, "🔥")

        lines = []
        if clean_title:
            lines.append(f"{emoji_hook} {clean_title}")
            lines.append("")

        if clean_summary:
            lines.append(clean_summary)
            lines.append("")

        if source and isinstance(source, str) and source.strip():
            clean_source = ContentSanitizer.sanitize_content(source.strip(), token=self.token)
            lines.append(f"📌 Source: {clean_source}")
            lines.append("")

        lines.append("💬 What do you think? Comment below!")
        lines.append("")

        generated_tags = HashtagGenerator.generate_hashtags(
            category=category_clean,
            custom_hashtags=hashtags,
            limit=max_hashtags,
        )
        lines.append(" ".join(generated_tags))

        raw_caption = "\n".join(lines).strip()
        sanitized_caption = ContentSanitizer.sanitize_content(raw_caption, token=self.token)

        CaptionValidator.validate_caption(sanitized_caption, token=self.token)

        return sanitized_caption
