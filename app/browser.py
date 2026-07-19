"""Playwright browser lifecycle.

Chromium is restarted for every extraction so the process fully releases
its heap between requests. On memory-constrained hosts (512 MB free tier)
a persistent browser accumulates renderer cache and V8 bytecode that the
OS never reclaims until the process exits, causing OOM after a few runs.

The small (~1-2s) restart overhead is acceptable for a demo deployment.
"""

import asyncio
from contextlib import asynccontextmanager

from playwright.async_api import Browser, Playwright, async_playwright

MAX_CONCURRENT_PAGES = 1
DEFAULT_TIMEOUT_MS = 30_000

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

_LAUNCH_ARGS = [
    # Required when Chromium runs as root inside the container.
    "--no-sandbox",
    # /dev/shm is tiny in containers; use /tmp instead.
    "--disable-dev-shm-usage",
    # Hides navigator.webdriver so bot-detection challenges auto-pass.
    "--disable-blink-features=AutomationControlled",
    # Memory-reduction flags — critical on 512 MB free-tier hosts.
    "--disable-extensions",
    "--disable-default-apps",
    "--disable-sync",
    "--disable-background-networking",
    "--disable-features=TranslateUI",
    "--no-first-run",
    # Cap the V8 old-generation heap to ~100 MB per renderer process.
    "--js-flags=--max-old-space-size=100",
]


class BrowserManager:
    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_PAGES)

    async def start(self) -> None:
        self._playwright = await async_playwright().start()

    async def stop(self) -> None:
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    async def _launch(self) -> Browser:
        if self._playwright is None:
            raise RuntimeError("BrowserManager.start() was never called")
        return await self._playwright.chromium.launch(
            headless=True,
            args=_LAUNCH_ARGS,
        )

    @asynccontextmanager
    async def page(self, js_enabled: bool = True):
        # js_enabled=False is used for uploaded HTML: the page is already
        # rendered, and letting its scripts re-bootstrap could wipe the DOM.
        async with self._semaphore:
            # Fresh browser process per extraction — fully releases all
            # renderer heap and cached data between requests.
            browser = await self._launch()
            try:
                context = await browser.new_context(
                    user_agent=USER_AGENT,
                    viewport={"width": 1280, "height": 900},
                    locale="en-US",
                    java_script_enabled=js_enabled,
                )
                page = await context.new_page()
                page.set_default_timeout(DEFAULT_TIMEOUT_MS)
                try:
                    yield page
                finally:
                    await context.close()
            finally:
                await browser.close()


browser_manager = BrowserManager()
