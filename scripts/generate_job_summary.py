import json
import os
import sys

def main():
    run_id = os.environ.get('GITHUB_RUN_ID', 'N/A')
    sha = os.environ.get('GITHUB_SHA', 'N/A')
    prep_file = 'data/prepared_media.json'
    proof_file = 'data/production_proof.json'
    
    summary = []
    summary.append('## TechCricketHub Instagram Publisher Execution Summary')
    summary.append(f'- **Run ID**: `{run_id}`')
    summary.append(f'- **Commit SHA**: `{sha}`')
    
    if os.path.exists(proof_file):
        try:
            with open(proof_file, 'r', encoding='utf-8') as f:
                pr = json.load(f)
            summary.append(f'- **Final Result Classification**: **{pr.get("status", "N/A")}**')
            summary.append(f'- **Live Reel Verified**: `{pr.get("live_reel_verified", False)}`')
            if pr.get('instagram_media_id'):
                summary.append(f'- **Instagram Media ID**: `{pr.get("instagram_media_id")}`')
            if pr.get('meta_creation_id'):
                summary.append(f'- **Meta Container ID**: `{pr.get("meta_creation_id")}`')
            if pr.get('instagram_permalink'):
                summary.append(f'- **Permalink**: {pr.get("instagram_permalink")}')
        except Exception as e:
            summary.append(f'- **Proof Load Error**: `{e}`')
    elif os.path.exists(prep_file):
        summary.append('- **Final Result Classification**: **PREPARED_WAITING_PUBLICATION**')
    else:
        summary.append('- **Final Result Classification**: **HEALTHY_NO_CONTENT**')

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
