"""Extractor for Gemini share links.

Handles both URL styles:
  - share.gemini.google/<id>           (short share domain)
  - gemini.google.com/share/<id>       (canonical) / g.co/gemini/share/<id>

Share pages (verified 2026-07 against a live page) render turns as:
  <share-turn-viewer>
    <user-query> ... <p class="query-text-line">hi</p>
    <response-container> ... <message-content>...</message-content>
  </share-turn-viewer>

User content must come from .query-text-line specifically: its parent
.query-text also holds a visually-hidden "You said" screen-reader label
that inner_text picks up.

The in-app <model-response> element is kept as an assistant fallback in case
some share variants still use it. The conversation title is the page h1;
og:title is just generic Gemini branding.
"""

import re

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from app.extractors.base import BaseExtractor, ExtractionError
from app.models import Conversation

USER_SELECTOR = "user-query"
ASSISTANT_SELECTOR = "response-container, model-response"
USER_CONTENT_SELECTOR = ".query-text-line"
ASSISTANT_CONTENT_SELECTOR = "message-content"
TITLE_SELECTOR = ".share-title-section h1, h1.headline"


class GeminiExtractor(BaseExtractor):
    platform = "gemini"

    def detect(self, url: str) -> bool:
        return (
            re.search(r"share\.gemini\.google/", url) is not None
            or re.search(r"gemini\.google\.com/share/", url) is not None
            or re.search(r"g\.co/gemini/share", url) is not None
        )

    def detect_html(self, html: str) -> bool:
        return (
            "<user-query" in html
            or "<response-container" in html
            or "<model-response" in html
        )

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
                "No messages found on the Gemini share page. The link may be "
                "expired or private, or the page structure may have changed."
            )
        if not messages:
            await self._log_failure(page, url)
            raise ExtractionError("The Gemini share page contained no message text.")
        return Conversation(
            platform=self.platform,
            title=await self._gemini_title(page),
            source_url=url,
            messages=messages,
        )

    async def _gemini_title(self, page: Page) -> str:
        h1 = page.locator(TITLE_SELECTOR)
        if await h1.count():
            text = (await h1.first.inner_text()).strip()
            if text:
                return text
        return await self._title(page)
