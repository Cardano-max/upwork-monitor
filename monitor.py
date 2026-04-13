#!/usr/bin/env python3
"""
Upwork Job Monitor - Headless browser + ntfy.sh push notifications
Runs every 5 minutes. Zero Claude tokens. Deployable on cloud.
Uses Playwright (headless Chromium) to bypass Upwork's anti-scraping.
"""

import json
import re
import hashlib
import time
import os
import sys
import requests
from datetime import datetime
from pathlib import Path

# ============ CONFIG ============
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "ateeb-upwork-2026")
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", 300))  # 5 min default
MAX_AGE_MINUTES = int(os.environ.get("MAX_AGE_MINUTES", 10))
UPWORK_URL = "https://www.upwork.com/nx/find-work/most-recent"
SEEN_JOBS_FILE = Path(__file__).parent / "seen_jobs.json"
COOKIES_FILE = Path(__file__).parent / "upwork_cookies.json"
SINGLE_RUN = os.environ.get("SINGLE_RUN", "false").lower() == "true"

# Upwork login credentials (set via env vars for cloud)
UPWORK_EMAIL = os.environ.get("UPWORK_EMAIL", "")
UPWORK_PASSWORD = os.environ.get("UPWORK_PASSWORD", "")

KEYWORDS = [
    "llm", "rag", "langchain", "langgraph", "mcp", "multi-agent", "ai agent",
    "vector database", "agentic", "fastapi", "python ai", "reinforcement learning",
    "nlp", "gpt", "claude", "ml engineer", "machine learning", "deep learning",
    "transformer", "embedding", "fine-tuning", "fine tuning", "chatbot",
    "ai assistant", "ai automation", "prompt engineering", "document ai",
    "pdf extraction", "computer vision", "tensorflow", "pytorch", "huggingface",
    "openai", "anthropic", "ai development", "neural network", "model training",
    "mlops", "ai pipeline", "knowledge graph", "semantic search",
    "conversational ai", "voice ai", "speech recognition", "ai developer",
    "artificial intelligence", "data science", "generative ai", "diffusion",
    "langsmith", "crewai", "autogen", "llamaindex", "pinecone", "chromadb",
    "weaviate", "qdrant", "ai scraping", "ai web", "ai saas",
    "n8n", "automation", "workflow automation", "zapier", "make.com",
]


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def load_seen_jobs():
    if SEEN_JOBS_FILE.exists():
        try:
            data = json.loads(SEEN_JOBS_FILE.read_text())
            if len(data) > 500:
                data = dict(list(data.items())[-500:])
            return data
        except Exception:
            return {}
    return {}


def save_seen_jobs(seen):
    SEEN_JOBS_FILE.write_text(json.dumps(seen, indent=2))


def job_hash(title, url):
    return hashlib.md5(f"{title}:{url}".encode()).hexdigest()


def matches_keywords(text):
    text_lower = text.lower()
    return [kw for kw in KEYWORDS if kw in text_lower]


def send_ntfy(title, message, priority="high"):
    try:
        resp = requests.post(
            NTFY_URL,
            headers={"Title": title, "Priority": priority, "Tags": "briefcase"},
            data=message.encode("utf-8"),
            timeout=10,
        )
        log(f"  NOTIFIED: {title}" if resp.ok else f"  ntfy error: {resp.status_code}")
    except Exception as e:
        log(f"  ntfy failed: {e}")


def parse_posted_time(text):
    if not text:
        return None
    text = text.lower().strip()
    if "just now" in text or "moment" in text or "second" in text:
        return 0
    m = re.search(r"(\d+)\s*min", text)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*hour", text)
    if m:
        return int(m.group(1)) * 60
    if "day" in text or "week" in text or "month" in text:
        return 9999
    return None


def check_jobs():
    from playwright.sync_api import sync_playwright
    log("=" * 50)
    log("Checking Upwork for new jobs...")
    seen = load_seen_jobs()
    new_matches = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
        )
        if COOKIES_FILE.exists():
            try:
                cookies = json.loads(COOKIES_FILE.read_text())
                context.add_cookies(cookies)
                log("  Loaded saved cookies")
            except Exception:
                pass

        page = context.new_page()
        try:
            log(f"  Loading {UPWORK_URL}")
            page.goto(UPWORK_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            current_url = page.url
            if "login" in current_url.lower() or "signin" in current_url.lower():
                log("  NOT LOGGED IN! Cookies expired or missing.")
                send_ntfy("Upwork Login Needed", "Cookies expired. Run login_save_cookies.py on your Mac.", "high")
                browser.close()
                return

            log("  Extracting job listings...")
            jobs_data = page.evaluate("""
                () => {
                    const jobs = [];
                    const cards = document.querySelectorAll(
                        'article[data-test="JobTile"], .job-tile, [data-ev-sublocation="jst_list_item"], section.up-card-section, .air3-card-section'
                    );
                    for (const card of cards) {
                        try {
                            const titleEl = card.querySelector('h2 a, h3 a, .job-title a, a[data-test="job-tile-title-link"], a.up-n-link, .air3-link');
                            const title = titleEl ? titleEl.textContent.trim() : '';
                            const url = titleEl ? titleEl.href : '';
                            const timeEl = card.querySelector('time, [data-test="posted-on"], .job-posted-on, small[data-test="job-pubilshed-date"], span[data-test="posted-on"]');
                            const posted = timeEl ? timeEl.textContent.trim() : '';
                            const descEl = card.querySelector('.job-description, [data-test="JobDescription"], [data-test="job-description-text"], .air3-line-clamp');
                            const desc = descEl ? descEl.textContent.trim().slice(0, 300) : '';
                            const budgetEl = card.querySelector('[data-test="budget"], [data-test="is-fixed-price"], .budget, [data-test="job-type-label"]');
                            const budget = budgetEl ? budgetEl.textContent.trim() : 'N/A';
                            const propsEl = card.querySelector('[data-test="proposals"], .proposals');
                            const proposals = propsEl ? propsEl.textContent.trim() : '?';
                            const skillEls = card.querySelectorAll('[data-test="token"] span, .air3-token span, .up-skill-badge');
                            const skills = Array.from(skillEls).map(s => s.textContent.trim()).join(', ');
                            if (title) jobs.push({ title, url, posted, desc, budget, proposals, skills });
                        } catch(e) { continue; }
                    }
                    if (jobs.length === 0) return { raw: document.body.innerText.slice(0, 10000), jobs: [] };
                    return { jobs, raw: null };
                }
            """)

            jobs = jobs_data.get("jobs", [])
            raw_text = jobs_data.get("raw", "")
            if not jobs and raw_text:
                log(f"  No structured cards found. Trying raw text...")
                lines = raw_text.split("\n")
                current_job = {}
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    if re.search(r"posted\s+\d+\s+minutes?\s+ago", line, re.I):
                        if current_job.get("title"):
                            current_job["posted"] = line
                            jobs.append(current_job)
                        current_job = {}
                    elif len(line) > 20 and len(line) < 200 and not current_job.get("title"):
                        current_job = {"title": line, "url": "", "desc": "", "budget": "N/A", "proposals": "?", "skills": "", "posted": ""}

            log(f"  Found {len(jobs)} job listings")
            for job in jobs:
                title = job.get("title", "")
                url = job.get("url", "")
                jid = job_hash(title, url)
                if jid in seen:
                    continue
                posted = job.get("posted", "")
                minutes = parse_posted_time(posted)
                if minutes is not None and minutes > MAX_AGE_MINUTES:
                    seen[jid] = datetime.now().isoformat()
                    continue
                full_text = f"{title} {job.get('desc', '')} {job.get('skills', '')}"
                matched = matches_keywords(full_text)
                if not matched:
                    seen[jid] = datetime.now().isoformat()
                    continue
                new_matches += 1
                seen[jid] = datetime.now().isoformat()
                kw_str = ", ".join(matched[:5])
                msg = f"JOB: {title}\nBudget: {job.get('budget', 'N/A')}\nPosted: {posted or 'Recent'}\nProposals: {job.get('proposals', '?')}\nKeywords: {kw_str}\nURL: {url}"
                log(f"\n  >> NEW MATCH: {title}")
                log(f"     Keywords: {kw_str}")
                send_ntfy("New Upwork Job!", msg)

        except Exception as e:
            log(f"  ERROR: {e}")
            send_ntfy("Upwork Monitor Error", f"Error: {str(e)[:200]}", "default")
        finally:
            try:
                cookies = context.cookies()
                COOKIES_FILE.write_text(json.dumps(cookies, indent=2))
            except Exception:
                pass
            browser.close()

    save_seen_jobs(seen)
    if new_matches == 0:
        log("  No new matching jobs.")
    else:
        log(f"  TOTAL NEW MATCHES: {new_matches}")


def main():
    log("=" * 50)
    log("UPWORK JOB MONITOR (Playwright)")
    log(f"ntfy: {NTFY_TOPIC} | interval: {CHECK_INTERVAL}s")
    log(f"Keywords: {len(KEYWORDS)}")
    log("=" * 50)
    send_ntfy("Upwork Monitor Started", f"Checking every {CHECK_INTERVAL // 60} min", "default")
    if SINGLE_RUN:
        check_jobs()
        return
    while True:
        try:
            check_jobs()
        except Exception as e:
            log(f"CRITICAL: {e}")
            send_ntfy("Monitor Crash", str(e)[:200], "default")
        log(f"Sleeping {CHECK_INTERVAL // 60} min...")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
