"""Extractor for Kimi (Moonshot AI) share links (kimi.com/share/... or
kimi.moonshot.cn/share/...).

Share pages are served fully server-rendered by a dedicated SEO build
(verified 2026-07 against a live page), so the conversation DOM exists at
domcontentloaded — no client-side rendering wait, which also means no
slow-CPU problem on Render. Turns render as:

  <div class="segment segment-user">
    ... <div class="user-content">text</div>
  <div class="segment segment-assistant">
    ... <div class="markdown-container"><div class="markdown">...</div></div>

Content selectors matter: the segment element also contains avatar and
card chrome. The conversation title is <h2 class="share-title">.
"""

import re

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from app.extractors.base import BaseExtractor, ExtractionError
from app.models import Conversation

USER_SELECTOR = ".segment-user"
ASSISTANT_SELECTOR = ".segment-assistant"
USER_CONTENT_SELECTOR = ".user-content"
ASSISTANT_CONTENT_SELECTOR = ".markdown-container"
TITLE_SELECTOR = "h2.share-title"


class KimiExtractor(BaseExtractor):
    platform = "kimi"

    def detect(self, url: str) -> bool:
        return (
            re.search(r"(www\.)?kimi\.com/share/", url) is not None
            or re.search(r"kimi\.moonshot\.cn/share/", url) is not None
        )

    def detect_html(self, html: str) -> bool:
        return "segment-user" in html and "segment-assistant" in html

    async def parse(self, page: Page, url: str) -> Conversation:
        try:
            messages = await self._extract_role_pairs(
                page,
                USER_SELECTOR,
                ASSISTANT_SELECTOR,
                user_content_selector=USER_CONTENT_SELECTOR,
                assistant_content_selector=ASSISTANT_CONTENT_SELECTOR,
            )
        except PlaywrightTimeout:
            await self._log_failure(page, url)
            raise ExtractionError(
                "No messages found on the Kimi share page. The link may be "
                "expired or private, or the page structure may have changed."
            )
        if not messages:
            await self._log_failure(page, url)
            raise ExtractionError("The Kimi share page contained no message text.")
        return Conversation(
            platform=self.platform,
            title=await self._kimi_title(page),
            source_url=url,
            messages=messages,
        )

    async def _kimi_title(self, page: Page) -> str:
        h2 = page.locator(TITLE_SELECTOR)
        if await h2.count():
            text = (await h2.first.inner_text()).strip()
            if text:
                return text
        # <title> is "Kimi | <conversation title>"
        return (await self._title(page)).removeprefix("Kimi |").strip()
