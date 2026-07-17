"""Playwright browser lifecycle.

One Chromium process is launched at app startup and shared by all requests.
Each request gets its own (cheap, isolated) browser context. A semaphore
caps concurrent pages because the Render instance has limited RAM.
"""

import asyncio
from contextlib import asynccontextmanager

from playwright.async_api import Browser, Playwright, async_playwright

MAX_CONCURRENT_PAGES = 2
DEFAULT_TIMEOUT_MS = 30_000

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


class BrowserManager:
    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_PAGES)

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                # Required when Chromium runs as root inside the container.
                "--no-sandbox",
                # /dev/shm is tiny in containers; use /tmp instead.
                "--disable-dev-shm-usage",
            ],
        )

    async def stop(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    @asynccontextmanager
    async def page(self, js_enabled: bool = True):
        # js_enabled=False is used for uploaded HTML: the page is already
        # rendered, and letting its scripts re-bootstrap could wipe the DOM.
        if self._browser is None:
            raise RuntimeError("BrowserManager.start() was never called")
        async with self._semaphore:
            context = await self._browser.new_context(
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


browser_manager = BrowserManager()
