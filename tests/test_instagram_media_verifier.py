import os
import pytest
from instagram_media_verifier import InstagramMediaVerifier


def test_media_verifier_invalid_scheme(tmp_path):
    verifier = InstagramMediaVerifier(history_dir=str(tmp_path))
    res = verifier.verify_and_deduplicate("http://insecure.com/image.jpg")
    assert res.is_valid is False
    assert res.error_code == "INVALID_SCHEME"


def test_media_verifier_magic_bytes():
    verifier = InstagramMediaVerifier()
    # JPEG magic bytes
    assert verifier.check_magic_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF", "IMAGE") is True
    # PNG magic bytes
    assert verifier.check_magic_bytes(b"\x89PNG\r\n\x1a\n\x00\x00", "IMAGE") is True
    # MP4 magic bytes
    assert verifier.check_magic_bytes(b"\x00\x00\x00\x18ftypmp42", "REEL") is True
    # Invalid bytes
    assert verifier.check_magic_bytes(b"INVALID_MAGIC_BYTES_TEXT", "IMAGE") is False


def test_media_verifier_duplicate_detection(tmp_path):
    verifier = InstagramMediaVerifier(history_dir=str(tmp_path))
    sample_hash = "11223344556677889900aabbccddeeff"
    verifier.record_media(sample_hash)

    assert verifier.is_duplicate_media(sample_hash) is True
    assert verifier.is_duplicate_media("non_existent_hash") is False


def test_media_verifier_canonical_url_deduplication(tmp_path):
    verifier = InstagramMediaVerifier(history_dir=str(tmp_path))
    url1 = "https://www.espncricinfo.com/story/123?utm_source=rss&utm_medium=feed"
    url2 = "https://www.espncricinfo.com/story/123?utm_source=twitter&utm_medium=social"

    c1 = verifier.canonicalize_url(url1)
    c2 = verifier.canonicalize_url(url2)
    assert c1 == c2

    verifier.record_article(url1)
    assert verifier.is_duplicate_article(url2) is True
