# Upwork Job Monitor

Automated Upwork job monitoring with push notifications via ntfy.sh.

## Features
- Playwright headless browser (bypasses Upwork anti-scraping)
- 65+ AI/ML keyword matching
- ntfy.sh push notifications to iPhone/Android
- Cookie-based auth (no password in code)
- Deployable: Local, Docker, Railway, GitHub Actions

## Quick Start

1. Install dependencies:
\`\`\`bash
pip install -r requirements.txt
playwright install chromium
\`\`\`

2. Login to Upwork (one-time):
\`\`\`bash
python3 login_save_cookies.py
\`\`\`

3. Install ntfy app on your phone, subscribe to topic: ateeb-upwork-2026

4. Run the monitor:
\`\`\`bash
python3 monitor.py
\`\`\`

## Deploy on GitHub Actions
The included workflow runs every 5 minutes via cron.
Upload your upwork_cookies.json as a GitHub Actions secret.

## Deploy on Docker/Railway
\`\`\`bash
docker build -t upwork-monitor .
docker run -v ./upwork_cookies.json:/app/upwork_cookies.json upwork-monitor
\`\`\`
