# TechCricketHub Instagram Automation — Project Rules & Guidelines

## 1. Production Architecture & Deployment Rules
- **Execution Platform**: Production publishing runs **exclusively via GitHub Actions** (`.github/workflows/instagram-publisher.yml`).
- **Forbidden Hosting/Integrations**:
  - Do NOT introduce Render, Railway, Docker hosting, external servers, databases, or cloud databases.
  - Do NOT introduce Telegram bots, webhooks, or third-party messaging services.
  - Do NOT alter Meta Graph API authentication or publishing pipeline architecture.

## 2. Real Video & Rights Evidence Enforcement
- **Real Video Only**: Accept ONLY actual MP4/MOV video files.
- **Forbidden Media**:
  - No image-to-video conversions.
  - No synthetic or AI-generated sports footage.
  - No synthetic cricket match clips.
  - No copyrighted match footage without explicit, verified reuse rights.
- **Item-Level Rights Verification**:
  - Every prepared candidate must contain `rights_status`, `rights_evidence`, `license_url`, and `commercial_use_allowed`.
  - Ambiguous or unverified rights are automatically rejected.

## 3. Factual Caption, SEO & Anti-Hallucination Rules
- **Verified Sources Only**: Captions must be generated strictly from verified source metadata (`title`, `summary`, `facts`).
- **Never Invent**: Scores, player quotes, statistics, match results, injuries, transfer information, dates, or locations.
- **5-Part Reel Caption Structure**:
  1. **HOOK**: Uppercase, high-impact headline grounded in verified text.
  2. **BODY**: 2 to 4 factual sentences summarizing verified source context.
  3. **KEY DETAIL**: Highlighted focal point or entity.
  4. **CALL TO ACTION**: Non-repetitive, rotated engagement prompt.
  5. **SEO & HASHTAGS**: Category-specific hashtags (Cricket vs Tech).
- **Anti-Clickbait & Duplication**:
  - Sensationalist clickbait terms (`SHOCKING`, `UNBELIEVABLE`, etc.) are strictly forbidden.
  - Captions with >0.50 Jaccard similarity to published history are rejected.

## 4. Production Reel Quality Engine
- **Vertical 9:16 Aspect Ratio**: Aspect ratio must be between 0.50 and 0.62 (target 9:16 = 0.5625). Horizontal or square videos are rejected.
- **Resolution**: Minimum resolution of 540x960 (recommended 1080x1920).
- **Frame Rate & Duration**: Valid frame rate (20.0 to 60.0 fps) and duration (3.0s to 90.0s).
- **Audio & Stream Integrity**: Audio stream present where available, no corrupted frames, no black/empty video, no static single-frame loops, and text overlays must respect top 150px / bottom 250px safe margins.

## 5. Content Intelligence & Category Balancing
- Maintain ~75% Cricket content and ~25% Tech content over the rolling last 30 published items.
- Elevate Cricket priority during live matches, major tournaments, finals, and breaking cricket news.
