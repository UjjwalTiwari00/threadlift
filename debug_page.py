"""Throwaway debug script: open a URL like the app does and report what's there."""

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

from app.browser import USER_AGENT

CANDIDATES = [
    '[data-testid="user-message"]',
    ".font-claude-message",
    '[data-test-render-count]',
    "[data-message-author-role]",
    "user-query",
    "model-response",
    "article",
    "main",
]


async def main(url: str) -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        page = await context.new_page()
        resp = await page.goto(url, wait_until="domcontentloaded")
        print("status:", resp.status if resp else "?")
        await page.wait_for_timeout(8000)  # give the SPA time to render
        print("title:", await page.title())
        for sel in CANDIDATES:
            print(f"{sel!r}: {await page.locator(sel).count()} elements")
        body_text = (await page.locator("body").inner_text()).strip()
        print("--- body text (first 500 chars) ---")
        print(body_text[:500])
        Path("debug_dump.html").write_text(await page.content(), encoding="utf-8")
        print("--- full rendered HTML saved to debug_dump.html ---")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
