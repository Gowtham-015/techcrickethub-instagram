import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from instagram_caption_generator import ContentSanitizer, HashtagGenerator, CaptionValidator
from security import redact_token

logger = logging.getLogger("InstagramFactualCaptionEngine")


CLICKBAIT_TERMS: Set[str] = {
    "you won't believe", "mind blown", "secret trick", "destroyed", "shocking truth",
    "unbelievable secret", "miracle", "insane hack", "blow your mind",
}

CRICKET_DEFAULT_HASHTAGS: List[str] = [
    "#TechCricketHub", "#Cricket", "#CricketNews", "#CricketReels", "#IndianCricket",
    "#MatchUpdate", "#T20", "#CricketHighlights", "#CricketFans",
]

TECH_DEFAULT_HASHTAGS: List[str] = [
    "#TechCricketHub", "#TechNews", "#Technology", "#AI", "#Innovation",
    "#TechUpdate", "#Gadgets", "#Software", "#TechTrends",
]

DYNAMIC_CTAS: List[str] = [
    "💬 What are your thoughts on this update? Comment below! 👇",
    "📌 Follow @techcrickethub for daily cricket & tech insights! What do you think? 👇",
    "🔥 Share your perspective in the comments below! Follow @techcrickethub 📲",
    "⚡ What is your take on this? Drop a comment below! 👇",
]


@dataclass
class CaptionGenerationResult:
    is_valid: bool
    caption: str
    hook: str
    body_sentences: List[str]
    key_detail: str
    cta: str
    hashtags: List[str]
    has_hallucinations: bool
    is_duplicate: bool
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "caption": self.caption,
            "hook": self.hook,
            "body_sentences": self.body_sentences,
            "key_detail": self.key_detail,
            "cta": self.cta,
            "hashtags": self.hashtags,
            "has_hallucinations": self.has_hallucinations,
            "is_duplicate": self.is_duplicate,
            "reasons": self.reasons,
        }


class FactualityVerifier:
    """Verifies that generated caption content contains only facts present in source text."""

    @staticmethod
    def extract_facts(text: str) -> Dict[str, Set[str]]:
        if not text:
            return {"numbers": set(), "quotes": set(), "scores": set()}

        # Extract scores like 200/4, 3-1, 100-2
        scores = set(re.findall(r"\b\d+[\/\-]\d+\b", text))

        # Extract numbers (excluding small common counts like 1, 2)
        numbers = set(re.findall(r"\b\d{2,}\b", text))

        # Extract quotes inside "..." or '...' (avoiding contractions like Women's, it's)
        quotes = set(re.findall(r'"([^"]+)"', text))
        quotes.update(re.findall(r"(?<=[\s\(\[\{])'([^']+)'(?=[\s\)\.\,\!\?\]\}])", text))

        return {"numbers": numbers, "quotes": quotes, "scores": scores}

    def verify_factuality(self, caption_text: str, source_text: str) -> Tuple[bool, List[str]]:
        reasons = []
        if not caption_text:
            return False, ["Caption text is empty."]

        cap_facts = self.extract_facts(caption_text)
        src_facts = self.extract_facts(source_text)
        src_lower = source_text.lower() if source_text else ""

        # 1. Verify scores
        for score in cap_facts["scores"]:
            if score not in src_facts["scores"] and score not in src_lower:
                reasons.append(f"Hallucinated score detected: '{score}' not present in verified source text.")

        # 2. Verify numbers
        for num in cap_facts["numbers"]:
            if num not in src_facts["numbers"] and num not in src_lower:
                reasons.append(f"Hallucinated numeric stat detected: '{num}' not present in verified source text.")

        # 3. Verify quotes
        for quote in cap_facts["quotes"]:
            if len(quote) > 5 and quote.lower() not in src_lower:
                reasons.append(f"Hallucinated quote detected: '{quote[:30]}...' not present in source text.")

        # 4. Clickbait check
        cap_lower = caption_text.lower()
        for cb in CLICKBAIT_TERMS:
            if cb in cap_lower:
                reasons.append(f"Clickbait term detected: '{cb}'.")

        is_factual = len(reasons) == 0
        return is_factual, reasons


class InstagramFactualCaptionEngine:
    """Production-safe Factual Caption, SEO & Hashtag Engine.

    Guarantees captions are derived strictly from verified source information,
    eliminates hallucinated stats/scores/quotes, builds a structured 5-part format
    (Hook, Body, Key Detail, CTA, SEO Hashtags), prevents duplicate/similar captions,
    and enforces category-specific terminology.
    """

    def __init__(self, token: Optional[str] = None):
        self.token = token
        self.verifier = FactualityVerifier()

    def _split_sentences(self, text: str) -> List[str]:
        if not text:
            return []
        raw_sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        clean = [s.strip() for s in raw_sentences if len(s.strip()) > 10]
        return clean

    def calculate_caption_similarity(self, cap1: str, cap2: str) -> float:
        if not cap1 or not cap2:
            return 0.0
        w1 = set(re.findall(r"\b[a-z0-9]+\b", cap1.lower()))
        w2 = set(re.findall(r"\b[a-z0-9]+\b", cap2.lower()))
        if not w1 or not w2:
            return 0.0
        intersection = len(w1.intersection(w2))
        union = len(w1.union(w2))
        return intersection / union if union > 0 else 0.0

    def check_duplicate_caption(
        self, caption: str, published_history: List[Dict[str, Any]], threshold: float = 0.50
    ) -> Tuple[bool, float]:
        if not caption or not published_history:
            return False, 0.0

        # Extract core content (title & body text) before CTA / Hashtags for accurate similarity
        core_cap = caption.split("💬")[0].split("📌")[0].strip()

        recent_history = published_history[-20:] if len(published_history) > 20 else published_history
        for item in reversed(recent_history):
            prev_cap = item.get("caption") or item.get("title") or ""
            if prev_cap:
                prev_core = prev_cap.split("💬")[0].split("📌")[0].strip()
                sim = self.calculate_caption_similarity(core_cap, prev_core)
                if sim >= threshold:
                    return True, round(sim, 2)
        return False, 0.0

    def generate_factual_caption(
        self,
        title: str,
        summary: str,
        category: str = "cricket",
        source_domain: Optional[str] = None,
        published_history: Optional[List[Dict[str, Any]]] = None,
        item_index: int = 0,
    ) -> CaptionGenerationResult:
        category_clean = (category or "cricket").strip().lower()
        clean_title = ContentSanitizer.sanitize_content(title or "", token=self.token)
        clean_summary = ContentSanitizer.sanitize_content(summary or "", token=self.token)

        source_text = f"{clean_title} {clean_summary}"
        if not clean_title and not clean_summary:
            return CaptionGenerationResult(
                is_valid=False,
                caption="",
                hook="",
                body_sentences=[],
                key_detail="",
                cta="",
                hashtags=[],
                has_hallucinations=False,
                is_duplicate=False,
                reasons=["Both title and summary are empty."],
            )

        # 1. Structured HOOK
        emoji = "🏆" if category_clean == "cricket" else "🚀"
        hook = f"{emoji} {clean_title}" if clean_title else f"{emoji} Verified {category_clean.capitalize()} Update"

        # 2. Structured BODY (2-4 factual sentences)
        sentences = self._split_sentences(clean_summary)
        if not sentences and clean_title:
            sentences = [clean_title]

        body_sentences = sentences[:4] if len(sentences) >= 4 else sentences
        body_text = " ".join(body_sentences)

        # 3. KEY DETAIL BOX
        key_detail = f"📌 Key Takeaway: Verified source reports {body_sentences[0]}" if body_sentences else f"📌 Key Detail: Verified source update."
        if len(key_detail) > 150:
            key_detail = key_detail[:147] + "..."

        # 4. Dynamic CALL TO ACTION
        cta_idx = item_index % len(DYNAMIC_CTAS)
        cta = DYNAMIC_CTAS[cta_idx]

        # 5. SEO HASHTAGS
        base_tags = CRICKET_DEFAULT_HASHTAGS if category_clean == "cricket" else TECH_DEFAULT_HASHTAGS
        hashtags = HashtagGenerator.generate_hashtags(category=category_clean, custom_hashtags=base_tags, limit=10)
        hashtag_str = " ".join(hashtags)

        # Assemble 5-Part Structured Caption
        caption_parts = [
            hook,
            "",
            body_text,
            "",
            key_detail,
            "",
            cta,
            "",
            hashtag_str,
        ]

        if source_domain:
            caption_parts.insert(5, f"🔗 Verified Source: {source_domain}")
            caption_parts.insert(6, "")

        final_caption = "\n".join(caption_parts).strip()
        final_caption = ContentSanitizer.sanitize_content(final_caption, token=self.token)

        # 6. Factuality & Anti-Hallucination Verification
        is_factual, fact_reasons = self.verifier.verify_factuality(final_caption, source_text)

        # 7. Duplicate Caption Check against History
        is_dup, sim_score = self.check_duplicate_caption(final_caption, published_history or [])
        reasons = list(fact_reasons)
        if is_dup:
            reasons.append(f"Caption similarity ({sim_score:.2f}) exceeds threshold 0.55 against recent published history.")

        # Validate caption format constraints
        try:
            CaptionValidator.validate_caption(final_caption, token=self.token)
        except Exception as e:
            is_factual = False
            reasons.append(f"Caption format validation error: {e}")

        is_valid = is_factual and not is_dup

        return CaptionGenerationResult(
            is_valid=is_valid,
            caption=final_caption,
            hook=hook,
            body_sentences=body_sentences,
            key_detail=key_detail,
            cta=cta,
            hashtags=hashtags,
            has_hallucinations=not is_factual,
            is_duplicate=is_dup,
            reasons=reasons,
        )
