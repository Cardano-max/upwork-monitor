#!/usr/bin/env python3
"""
One-time setup: Opens a browser window for manual Upwork login.
After you log in, press Enter in the terminal to save cookies.
These cookies are then used by monitor.py for headless scraping.
"""

import json
from pathlib import Path
from playwright.sync_api import sync_playwright

COOKIES_FILE = Path(__file__).parent / "upwork_cookies.json"

def main():
    print("=" * 50)
    print("UPWORK LOGIN - Save Cookies")
    print("=" * 50)
    print()
    print("A browser window will open.")
    print("1. Log into Upwork manually")
    print("2. Make sure you're on the dashboard/feed page")
    print("3. Come back here and press Enter")
    print()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
        )
        page = context.new_page()
        page.goto("https://www.upwork.com/ab/account-security/login")

        input("\n>>> Press Enter after you've logged in successfully...\n")

        cookies = context.cookies()
        COOKIES_FILE.write_text(json.dumps(cookies, indent=2))
        print(f"\nSaved {len(cookies)} cookies to {COOKIES_FILE}")
        print("You can now run monitor.py!")

        browser.close()


if __name__ == "__main__":
    main()
