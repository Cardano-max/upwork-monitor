#!/usr/bin/env python3
"""
Upwork Job Monitor - Headless browser + ntfy.sh push notifications
Runs every 5 minutes. Zero Claude tokens. Deployable on cloud.
Uses Playwright (headless Chromium) to bypass Upwork's anti-scraping.
Auto-login with playwright-stealth when cookies expire.
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

# Upwork login credentials (set via env vars / GitHub secrets)
UPWORK_EMAIL = os.environ.get("UPWORK_EMAIL", "")
UPWORK_PASSWORD = os.environ.get("UPWORK_PASSWORD", "")
UPWORK_SECRET_ANSWER = os.environ.get("UPWORK_SECRET_ANSWER", "")

KEYWORDS = [
    "llm", "rag", "langchain", "langgraph", "mcp", "multi-agent",
    "ai agent", "vector database", "agentic", "fastapi", "python ai",
    "reinforcement learning", "nlp", "gpt", "claude", "ml engineer",
    "machine learning", "deep learning", "transformer", "embedding",
    "fine-tuning", "fine tuning", "chatbot", "ai assistant", "ai automation",
    "prompt engineering", "document ai", "pdf extraction", "computer vision",
    "tensorflow", "pytorch", "huggingface", "openai", "anthropic",
    "ai development", "neural network", "model training", "mlops",
    "ai pipeline", "knowledge graph", "semantic search", "conversational ai",
    "voice ai", "speech recognition", "ai developer", "artificial intelligence",
    "data science", "generative ai", "diffusion", "langsmith", "crewai",
    "autogen", "llamaindex", "pinecone", "chromadb", "weaviate", "qdrant",
    "ai scraping", "ai web", "ai saas", "n8n", "automation",
    "workflow automation", "zapier", "make.com",
]


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


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


def attempt_login(page):
    """
    Try to log into Upwork when cookies have expired.
    Uses playwright-stealth to avoid Cloudflare bot detection.
    Returns True if login succeeded, False otherwise.
    """
    if not UPWORK_EMAIL or not UPWORK_PASSWORD:
        log("  No credentials set. Cannot auto-login.")
        log("  Set UPWORK_EMAIL and UPWORK_PASSWORD as GitHub secrets.")
        return False

    log("  Attempting auto-login with stealth...")

    try:
        # Step 1: Navigate to login page
        login_url = "https://www.upwork.com/ab/account-security/login"
        page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        # Check if Cloudflare challenge is present
        page_text = page.text_content("body") or ""
        if "checking your browser" in page_text.lower() or "just a moment" in page_text.lower():
            log("  Cloudflare challenge detected, waiting...")
            page.wait_for_timeout(10000)
            page_text = page.text_content("body") or ""
            if "checking your browser" in page_text.lower():
                log("  Cloudflare still blocking. Auto-login failed.")
                return False

        # Step 2: Fill email
        email_selectors = [
            '#login_username',
            'input[name="login[username]"]',
            'input[type="email"]',
            'input[placeholder*="email"]',
            'input[placeholder*="Username"]',
        ]
        email_filled = False
        for sel in email_selectors:
            try:
                el = page.wait_for_selector(sel, timeout=5000)
                if el:
                    el.fill(UPWORK_EMAIL)
                    email_filled = True
                    log("  Filled email field")
                    break
            except Exception:
                continue

        if not email_filled:
            log("  Could not find email field")
            return False

        # Click continue/next button
        continue_selectors = [
            '#login_password_continue',
            'button[type="submit"]',
            'button:has-text("Continue")',
            'button:has-text("Log In")',
        ]
        for sel in continue_selectors:
            try:
                btn = page.wait_for_selector(sel, timeout=3000)
                if btn:
                    btn.click()
                    log("  Clicked continue")
                    break
            except Exception:
                continue

        page.wait_for_timeout(3000)

        # Step 3: Fill password
        password_selectors = [
            '#login_password',
            'input[name="login[password]"]',
            'input[type="password"]',
        ]
        pass_filled = False
        for sel in password_selectors:
            try:
                el = page.wait_for_selector(sel, timeout=5000)
                if el:
                    el.fill(UPWORK_PASSWORD)
                    pass_filled = True
                    log("  Filled password field")
                    break
            except Exception:
                continue

        if not pass_filled:
            log("  Could not find password field")
            return False

        # Click login button
        login_selectors = [
            '#login_control_continue',
            'button[type="submit"]',
            'button:has-text("Log In")',
            'button:has-text("Continue")',
        ]
        for sel in login_selectors:
            try:
                btn = page.wait_for_selector(sel, timeout=3000)
                if btn:
                    btn.click()
                    log("  Clicked login")
                    break
            except Exception:
                continue

        page.wait_for_timeout(5000)

        # Step 4: Handle security question if present
        current_url = page.url
        page_text = page.text_content("body") or ""

        if "secret" in page_text.lower() or "security" in current_url.lower():
            if UPWORK_SECRET_ANSWER:
                log("  Security question detected, filling answer...")
                answer_selectors = [
                    'input[type="text"]',
                    'input[name*="answer"]',
                    'input[name*="deviceAuthorization"]',
                ]
                for sel in answer_selectors:
                    try:
                        el = page.wait_for_selector(sel, timeout=3000)
                        if el:
                            el.fill(UPWORK_SECRET_ANSWER)
                            break
                    except Exception:
                        continue
                # Submit
                for sel in ['button[type="submit"]', 'button:has-text("Continue")', 'button:has-text("Submit")']:
                    try:
                        btn = page.wait_for_selector(sel, timeout=3000)
                        if btn:
                            btn.click()
                            break
                    except Exception:
                        continue
                page.wait_for_timeout(5000)
            else:
                log("  Security question found but no UPWORK_SECRET_ANSWER set")
                return False

        # Step 5: Check if we're logged in now
        current_url = page.url
        if "login" not in current_url.lower() and "signin" not in current_url.lower():
            log("  AUTO-LOGIN SUCCESSFUL!")
            return True
        else:
            log(f"  Login may have failed. Current URL: {current_url}")
            return False

    except Exception as e:
        log(f"  Auto-login error: {e}")
        return False


def check_jobs():
    from playwright.sync_api import sync_playwright

    log("=" * 50)
    log("Checking Upwork for new jobs...")

    seen = load_seen_jobs()
    new_matches = 0

    with sync_playwright() as p:
        # Launch with stealth-friendly args
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--no-sandbox",
            ]
        )

        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
            locale="en-US",
            timezone_id="America/New_York",
        )

        # Apply stealth patches
        try:
            from playwright_stealth import stealth_sync
            stealth_sync(context)
            log("  Stealth mode enabled")
        except ImportError:
            log("  playwright-stealth not installed, running without stealth")

        # Load cookies
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

            # If not logged in, try auto-login
            if "login" in current_url.lower() or "signin" in current_url.lower():
                log("  NOT LOGGED IN! Cookies expired. Attempting auto-login...")

                login_success = attempt_login(page)

                if login_success:
                    # Save new cookies immediately
                    try:
                        new_cookies = context.cookies()
                        COOKIES_FILE.write_text(json.dumps(new_cookies, indent=2))
                        log("  Saved new cookies after login")
                    except Exception:
                        pass

                    # Navigate to jobs page
                    page.goto(UPWORK_URL, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(3000)

                    current_url = page.url
                    if "login" in current_url.lower():
                        log("  Still on login page after auto-login attempt")
                        send_ntfy(
                            "Upwork Login Failed",
                            "Auto-login didn't work. Run login_cdp.py on your Mac and update UPWORK_COOKIES_B64 secret.",
                            "high",
                        )
                        browser.close()
                        return
                    else:
                        send_ntfy(
                            "Upwork Auto-Login OK",
                            "Cookies expired but auto-login succeeded. Monitoring continues.",
                            "default",
                        )
                else:
                    send_ntfy(
                        "Upwork Login Needed",
                        "Cookies expired and auto-login failed. Run login_cdp.py on your Mac and update UPWORK_COOKIES_B64 secret.",
                        "high",
                    )
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
                if (jobs.length === 0)
                    return { raw: document.body.innerText.slice(0, 10000), jobs: [] };
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
                        current_job = {
                            "title": line, "url": "", "desc": "",
                            "budget": "N/A", "proposals": "?", "skills": "", "posted": ""
                        }

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
                msg = (
                    f"JOB: {title}\n"
                    f"Budget: {job.get('budget', 'N/A')}\n"
                    f"Posted: {posted or 'Recent'}\n"
                    f"Proposals: {job.get('proposals', '?')}\n"
                    f"Keywords: {kw_str}\n"
                    f"URL: {url}"
                )
                log(f"\n >> NEW MATCH: {title}")
                log(f"    Keywords: {kw_str}")
                send_ntfy("New Upwork Job!", msg)

        except Exception as e:
            log(f"  ERROR: {e}")
            send_ntfy("Upwork Monitor Error", f"Error: {str(e)[:200]}", "default")

        finally:
            # Always save cookies (they may have been refreshed during browsing)
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
    log("UPWORK JOB MONITOR (Playwright + Stealth)")
    log(f"ntfy: {NTFY_TOPIC} | interval: {CHECK_INTERVAL}s")
    log(f"Keywords: {len(KEYWORDS)}")
    log(f"Auto-login: {'ENABLED' if UPWORK_EMAIL else 'DISABLED (no credentials)'}")
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
