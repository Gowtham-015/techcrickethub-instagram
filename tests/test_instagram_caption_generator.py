import pytest
from exceptions import InstagramConfigError, InstagramError
from instagram_caption_generator import (
    CaptionValidator,
    ContentSanitizer,
    HashtagGenerator,
    InstagramCaptionGenerator,
)


def test_caption_generation_cricket():
    generator = InstagramCaptionGenerator()
    caption = generator.generate_caption(
        title="India wins final match of series",
        summary="An impressive bowling performance secured a decisive victory in the tournament final.",
        category="cricket",
        source="SportsDesk",
    )

    assert "🔥" in caption
    assert "India wins final match" in caption
    assert "📌 Source: SportsDesk" in caption
    assert "#TechCricketHub" in caption
    assert "#Cricket" in caption
    assert "💬 What do you think? Comment below!" in caption


def test_caption_generation_technology():
    generator = InstagramCaptionGenerator()
    caption = generator.generate_caption(
        title="AI breakthrough announced",
        summary="New neural network architecture reduces inference latency significantly.",
        category="technology",
    )

    assert "🚀" in caption
    assert "AI breakthrough announced" in caption
    assert "#TechCricketHub" in caption
    assert "#Technology" in caption


def test_caption_generation_entertainment():
    generator = InstagramCaptionGenerator()
    caption = generator.generate_caption(
        title="Movie teaser breaks trailer records",
        summary="The newly released teaser amassed millions of views within hours.",
        category="entertainment",
    )

    assert "🎬" in caption
    assert "#Entertainment" in caption


def test_caption_generation_sports():
    generator = InstagramCaptionGenerator()
    caption = generator.generate_caption(
        title="Championship match set for weekend",
        summary="Teams prepare for the high-stakes final event.",
        category="sports",
    )

    assert "🏆" in caption
    assert "#Sports" in caption


def test_missing_title_valid_summary():
    generator = InstagramCaptionGenerator()
    caption = generator.generate_caption(
        title="",
        summary="A detailed summary of the event provided without a title.",
        category="cricket",
    )
    assert "A detailed summary" in caption
    assert "#TechCricketHub" in caption


def test_missing_summary_valid_title():
    generator = InstagramCaptionGenerator()
    caption = generator.generate_caption(
        title="Headline Only Event",
        summary="",
        category="cricket",
    )
    assert "Headline Only Event" in caption


def test_empty_title_and_summary():
    generator = InstagramCaptionGenerator()
    with pytest.raises(InstagramConfigError) as exc_info:
        generator.generate_caption(title="", summary="")
    assert "both title and summary are empty" in str(exc_info.value)


def test_unicode_and_emojis():
    generator = InstagramCaptionGenerator()
    caption = generator.generate_caption(
        title="World Cup Victory! 🇮🇳🏆",
        summary="Team celebrates grand success with fans worldwide. ❤️🔥",
        category="cricket",
    )
    assert "🇮🇳🏆" in caption
    assert "❤️🔥" in caption


# Hashtag Generator Tests


def test_hashtag_generator_mandatory_tag():
    tags = HashtagGenerator.generate_hashtags(category="cricket", limit=5)
    assert tags[0] == "#TechCricketHub"


def test_hashtag_generator_deduplication():
    custom = ["#Cricket", "#cricket", "#CRICKET", "#NewTag"]
    tags = HashtagGenerator.generate_hashtags(category="cricket", custom_hashtags=custom)
    lower_tags = [t.lower() for t in tags]
    assert len(lower_tags) == len(set(lower_tags))


def test_hashtag_generator_normalization():
    norm = HashtagGenerator.normalize_hashtag("  !CricketNews!!  ")
    assert norm == "#CricketNews"


def test_hashtag_generator_limit():
    tags = HashtagGenerator.generate_hashtags(category="cricket", limit=3)
    assert len(tags) == 3


# Sanitization & Security Tests


def test_sanitizer_token_redaction():
    raw_text = "Headline with access_token=EAACEdEose0cBA123 secret inside"
    sanitized = ContentSanitizer.sanitize_content(raw_text)
    assert "EAACEdEose0cBA123" not in sanitized
    assert "access_token=[REDACTED]" in sanitized


def test_sanitizer_explicit_token():
    token = "MY_SECRET_API_KEY_123"
    raw_text = f"Content text containing secret {token}"
    sanitized = ContentSanitizer.sanitize_content(raw_text, token=token)
    assert token not in sanitized
    assert "[REDACTED]" in sanitized


def test_sanitizer_control_character_cleanup():
    raw_text = "Clean text \x00\x07with control chars\x1f stripped"
    sanitized = ContentSanitizer.sanitize_content(raw_text)
    assert "\x00" not in sanitized
    assert "\x07" not in sanitized
    assert "Clean text with control chars stripped" in sanitized


# Validation Tests


def test_validator_empty_caption():
    with pytest.raises(InstagramError) as exc_info:
        CaptionValidator.validate_caption("")
    assert "cannot be empty" in str(exc_info.value)


def test_validator_oversized_caption():
    long_caption = "a" * 2201
    with pytest.raises(InstagramError) as exc_info:
        CaptionValidator.validate_caption(long_caption)
    assert "exceeds Instagram's limit of 2200 characters" in str(exc_info.value)


def test_validator_excessive_hashtags():
    many_hashtags = " ".join([f"#tag{i}" for i in range(31)])
    with pytest.raises(InstagramError) as exc_info:
        CaptionValidator.validate_caption(many_hashtags)
    assert "exceeds maximum limit of 30 hashtags" in str(exc_info.value)


def test_validator_duplicate_hashtags():
    caption = "Sample text #Cricket #cricket #Sports"
    with pytest.raises(InstagramError) as exc_info:
        CaptionValidator.validate_caption(caption)
    assert "duplicate hashtags" in str(exc_info.value)


def test_validator_unredacted_access_token():
    caption = "Check this post out access_token=123456"
    with pytest.raises(InstagramError) as exc_info:
        CaptionValidator.validate_caption(caption)
    assert "unredacted access_token" in str(exc_info.value)


def test_validator_explicit_token_leak():
    token = "MY_PRIVATE_TOKEN_99"
    caption = f"Sample caption with {token}"
    with pytest.raises(InstagramError) as exc_info:
        CaptionValidator.validate_caption(caption, token=token)
    assert "unredacted secret token" in str(exc_info.value)


def test_validator_excessive_repeated_words():
    spam_caption = "spam " * 15
    with pytest.raises(InstagramError) as exc_info:
        CaptionValidator.validate_caption(spam_caption)
    assert "excessive repeated word spam" in str(exc_info.value)
