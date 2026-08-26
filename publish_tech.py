import os
import sys
import shutil
import requests
from config import Config
from instagram_real_news_source import InstagramRealNewsSource
from instagram_reel_generator import InstagramReelGenerator
from instagram_caption_generator import InstagramCaptionGenerator
from instagram_content_bundle import ContentBundle, ContentIntegrityValidator
from instagram_final_publish_guard import InstagramFinalPublishGuard
from instagram_media_verifier import InstagramMediaVerifier
from instagram_client import InstagramAPIClient
from instagram_reel_publisher import InstagramReelPublisher

def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print("========================================")
    print("REAL INSTAGRAM TECHNOLOGY POST / REEL")
    print("========================================")

    config = Config.load_from_env(validate=False)
    mode_label = "PRODUCTION" if config.production_enabled and not config.dry_run else "TEST / DRY_RUN"
    print(f"Mode: {mode_label}")
    print(f"Dry Run: {'TRUE' if config.dry_run else 'FALSE'}")
    print()

    source = InstagramRealNewsSource(config=config)
    items = source.get_content_items()
    tech_items = [i for i in items if i.get("category") == "technology"]

    if not tech_items:
        print("Story: FAIL (No Technology news items acquired from RSS feeds)")
        return False

    candidate = tech_items[0]
    content_id = candidate.get("content_id", "tech-reel-001")
    title = candidate.get("title", "Real Tech News Update")
    summary = candidate.get("summary", "Latest technology update.")
    source_name = candidate.get("source_name", "TechCrunch")
    category = "technology"

    print(f"Acquired Tech News Story:")
    print(f"  Title: {title}")
    print(f"  Summary: {summary}")
    print(f"  Source: {source_name}")
    print(f"  Category: {category}")

    # Generate vertical Reel video if not present
    video_url = candidate.get("video_url")
    if not video_url:
        print("\nGenerating Animated Vertical Video Reel from Tech Facts...")
        reel_gen = InstagramReelGenerator()
        reel_res = reel_gen.generate_reel_from_facts({
            "content_id": content_id,
            "title": title,
            "summary": summary,
            "source_name": source_name,
        })
        if reel_res.get("success") and reel_res.get("reel_path"):
            local_path = reel_res["reel_path"]
            rel_name = os.path.basename(local_path)
            gen_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media", "generated")
            os.makedirs(gen_dir, exist_ok=True)
            dst_path = os.path.join(gen_dir, rel_name)
            shutil.copy(local_path, dst_path)

            video_url = InstagramRealNewsSource.upload_to_public_host(dst_path, f"https://raw.githubusercontent.com/Gowtham-015/techcrickethub-instagram/main/media/generated/{rel_name}")
            print(f"Reel Video Public Host URL: {video_url}")

    if not video_url:
        print("ERROR: Failed to acquire or generate Reel video for Tech news.")
        return False

    caption_gen = InstagramCaptionGenerator()
    caption = caption_gen.generate_caption(
        title=title,
        summary=summary,
        category="technology",
        source=source_name,
    )

    bundle = ContentBundle(
        content_id=content_id,
        category=category,
        title=title,
        summary=summary,
        source_url=candidate.get("source_url", ""),
        source_domain=candidate.get("source_domain", ""),
        published_at=candidate.get("published_at", ""),
        media_url=video_url,
        media_type="REEL",
        media_rights_status=candidate.get("media_rights_status", "ORIGINAL_GENERATED"),
        caption=caption,
    )

    validator = ContentIntegrityValidator()
    val_res = validator.validate_bundle(bundle)
    print(f"\nContent Integrity: {'PASS' if val_res.is_valid else 'FAIL'}")

    guard = InstagramFinalPublishGuard(config=config)
    g_res = guard.verify_and_guard(bundle)
    print(f"Duplicate Guard: {'PASS' if g_res.is_valid else 'FAIL'}")

    if not g_res.is_valid:
        print(f"Guard Reason: {g_res.message}")
        return False

    if config.dry_run or not config.production_enabled:
        print("\nDRY_RUN mode active. Skipping Meta Graph API call.")
        return True

    try:
        client = InstagramAPIClient(user_id=config.user_id, access_token=config.access_token)
        reel_pub = InstagramReelPublisher(client=client)
        pub_res = reel_pub.publish_reel(video_url=video_url, caption=bundle.caption)

        print("\nMeta Graph API Publishing:")
        print(f"  Container Creation: {'PASS' if pub_res.creation_id else 'FAIL'}")
        print(f"  Container ID: {pub_res.creation_id}")
        print(f"  Processing Status: {'FINISHED' if pub_res.success else 'FAILED'}")
        print(f"  Media Publish: {'PASS' if pub_res.media_id else 'FAIL'}")

        is_confirmed = False
        if pub_res.success and pub_res.media_id:
            is_confirmed = client.verify_published_media(pub_res.media_id)

        print("\nInstagram Verification:")
        print(f"  Published Media ID: {pub_res.media_id or 'NONE'}")
        print(f"  Meta API Verification: {'PASS' if is_confirmed else 'FAIL'}")

        if pub_res.success and pub_res.media_id and is_confirmed:
            guard.record_published_item(bundle=bundle, media_id=pub_res.media_id)
            print("\nFINAL RESULT:")
            print("  ACTUAL INSTAGRAM TECH REEL PUBLISHED: YES")
            print("========================================")
            return True
        else:
            print("\nFINAL RESULT:")
            print("  ACTUAL INSTAGRAM TECH REEL PUBLISHED: NO")
            print(f"  REASON: {pub_res.message}")
            print("========================================")
            return False

    except Exception as e:
        print(f"Exception during publishing: {e}")
        return False

if __name__ == "__main__":
    main()
