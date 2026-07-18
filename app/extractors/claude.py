"""Extractor for Claude share links (claude.ai/share/...).

Claude's share pages are client-rendered and their DOM changes more often
than ChatGPT's. The selectors below match claude.ai at the time of writing;
when they break, update them and refresh tests/fixtures/claude.html.
"""

import re

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from app.extractors.base import BaseExtractor, ExtractionError
from app.models import Conversation

USER_SELECTOR = '[data-testid="user-message"]'
ASSISTANT_SELECTOR = ".font-claude-message"


class ClaudeExtractor(BaseExtractor):
    platform = "claude"

    def detect(self, url: str) -> bool:
        return re.search(r"claude\.ai/share/", url) is not None

    def detect_html(self, html: str) -> bool:
        return 'data-testid="user-message"' in html or "font-claude-message" in html

    async def parse(self, page: Page, url: str) -> Conversation:
        try:
            messages = await self._extract_role_pairs(
                page, USER_SELECTOR, ASSISTANT_SELECTOR
            )
        except PlaywrightTimeout:
            await self._log_failure(page, url)
            title = await page.title()
            if "just a moment" in title.lower():
                raise ExtractionError(
                    "claude.ai blocked the automated browser (Cloudflare bot "
                    "protection). Open the share link in your own browser, save "
                    "the page's HTML, and use the upload option instead."
                )
            raise ExtractionError(
                "No messages found on the Claude share page. The link may be "
                "expired or private, or the page structure may have changed. "
                "You can also open the link in your browser, save the HTML, "
                "and use the upload option."
            )
        if not messages:
            await self._log_failure(page, url)
            raise ExtractionError("The Claude share page contained no message text.")
        return Conversation(
            platform=self.platform,
            title=await self._title(page),
            source_url=url,
            messages=messages,
        )
