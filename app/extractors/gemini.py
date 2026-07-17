"""Extractor for Gemini share links (gemini.google.com/share/... or g.co/gemini/share/...).

Gemini is an Angular app that renders turns as custom elements
(<user-query> / <model-response>), which make convenient selectors.
"""

import re

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from app.extractors.base import BaseExtractor, ExtractionError
from app.models import Conversation

USER_SELECTOR = "user-query"
ASSISTANT_SELECTOR = "model-response"


class GeminiExtractor(BaseExtractor):
    platform = "gemini"

    def detect(self, url: str) -> bool:
        return (
            re.search(r"gemini\.google\.com/share/", url) is not None
            or re.search(r"g\.co/gemini/share", url) is not None
        )

    def detect_html(self, html: str) -> bool:
        return "<user-query" in html or "<model-response" in html

    async def parse(self, page: Page, url: str) -> Conversation:
        try:
            messages = await self._extract_role_pairs(
                page, USER_SELECTOR, ASSISTANT_SELECTOR
            )
        except PlaywrightTimeout:
            raise ExtractionError(
                "No messages found on the Gemini share page. The link may be "
                "expired or private, or the page structure may have changed."
            )
        if not messages:
            raise ExtractionError("The Gemini share page contained no message text.")
        return Conversation(
            platform=self.platform,
            title=await self._title(page),
            source_url=url,
            messages=messages,
        )
