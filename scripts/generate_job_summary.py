import json
import os
import sys

def main():
    run_id = os.environ.get('GITHUB_RUN_ID', 'N/A')
    sha = os.environ.get('GITHUB_SHA', 'N/A')
    prep_file = 'data/prepared_media.json'
    proof_file = 'data/production_proof.json'
    health_file = 'data/instagram_health.json'
    
    summary = []
    summary.append('## TechCricketHub Instagram Publisher Execution Summary')
    summary.append(f'- **Run ID**: `{run_id}`')
    summary.append(f'- **Commit SHA**: `{sha}`')
    
    published_count = 0
    status_label = "NO_VALID_REEL"
    
    if os.path.exists(proof_file):
        try:
            with open(proof_file, 'r', encoding='utf-8') as f:
                pr = json.load(f)
            
            is_live_pub = pr.get("live_reel_verified") or bool(pr.get("instagram_media_id"))
            if is_live_pub:
                published_count = 1
                status_label = "LIVE_REEL_PUBLISHED"
            elif pr.get("status") in ("NO_VALID_REEL", "NO_CANDIDATES"):
                status_label = "NO_VALID_REEL"
            elif pr.get("status") == "PUBLISH_FAILED":
                status_label = "PUBLISH_FAILED"
            else:
                status_label = pr.get("status", "NO_VALID_REEL")

            summary.append(f'- **Final Result Classification**: **{status_label}**')
            summary.append(f'- **Instagram Published**: `{published_count}`')

            if is_live_pub:
                if pr.get('instagram_media_id'):
                    summary.append(f'- **Instagram Media ID**: `{pr.get("instagram_media_id")}`')
                if pr.get('meta_creation_id'):
                    summary.append(f'- **Meta Container ID**: `{pr.get("meta_creation_id")}`')
                if pr.get('instagram_permalink'):
                    summary.append(f'- **Permalink**: {pr.get("instagram_permalink")}')
            else:
                reason = pr.get("reason") or pr.get("error") or status_label
                summary.append(f'- **Reason**: `{reason}`')
        except Exception as e:
            summary.append(f'- **Proof Load Error**: `{e}`')
    elif os.path.exists(prep_file):
        summary.append('- **Final Result Classification**: **PREPARED_WAITING_PUBLICATION**')
        summary.append('- **Instagram Published**: `0`')
    else:
        summary.append('- **Final Result Classification**: **NO_VALID_REEL**')
        summary.append('- **Instagram Published**: `0`')
        summary.append('- **Reason**: `NO_VALID_REEL`')

    if os.path.exists(health_file):
        try:
            with open(health_file, 'r', encoding='utf-8') as f:
                h = json.load(f)
            starvation_runs = h.get("consecutive_no_valid_reel_runs", 0)
            if starvation_runs >= 3:
                summary.append(f'- **Health Warning**: ⚠️ `CONTENT_STARVATION` ({starvation_runs} consecutive runs without valid Reels)')
            summary.append('### Pipeline Metrics')
            summary.append(f'- **Rights Rejections**: `{h.get("rights_rejection_count", 0)}`')
            summary.append(f'- **Quality Rejections**: `{h.get("video_quality_rejection_count", 0)}`')
            summary.append(f'- **Total Items Published**: `{h.get("items_published", 0)}`')
        except Exception:
            pass

    if os.path.exists(prep_file):
        try:
            with open(prep_file, 'r', encoding='utf-8') as f:
                p = json.load(f)
            summary.append('### Preparation Metadata')
            summary.append(f'- **Preparation ID**: `{p.get("preparation_id", "N/A")}`')
            summary.append(f'- **Content ID**: `{p.get("content_id", "N/A")}`')
            summary.append(f'- **Category**: `{p.get("category", "N/A")}`')
            sha_val = p.get("media_sha256", "N/A")
            short_sha = sha_val[:16] + '...' if sha_val != "N/A" else "N/A"
            summary.append(f'- **Media SHA256**: `{short_sha}`')
            summary.append(f'- **Rights Status**: `{p.get("media_rights_status", "N/A")}`')
            if p.get("information_source_url"):
                summary.append(f'- **Info Source URL**: {p.get("information_source_url")}')
            if p.get("media_source_url"):
                summary.append(f'- **Media Source URL**: {p.get("media_source_url")}')
            summary.append(f'- **Public URL**: {p.get("public_url", "N/A")}')
        except Exception as e:
            summary.append(f'- **Prep Load Error**: `{e}`')

    summary_path = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary_path:
        try:
            with open(summary_path, 'a', encoding='utf-8') as sf:
                sf.write('\n'.join(summary) + '\n')
            print("Step summary written successfully.")
        except Exception as e:
            print(f"Error writing step summary: {e}")
    else:
        print('\n'.join(summary))

if __name__ == '__main__':
    main()
