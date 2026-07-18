"""Extractor for ChatGPT share links (chatgpt.com/share/... or chat.openai.com/share/...).

ChatGPT share pages annotate every message with data-message-author-role,
which is far more stable than styling classes.
"""

import re

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from app.extractors.base import WAIT_FOR_MESSAGES_MS, BaseExtractor, ExtractionError
from app.models import Conversation, Message, Role

MESSAGE_SELECTOR = "[data-message-author-role]"
VALID_ROLES = ("user", "assistant", "system")


class ChatGPTExtractor(BaseExtractor):
    platform = "chatgpt"

    def detect(self, url: str) -> bool:
        return re.search(r"(chatgpt\.com|chat\.openai\.com)/share/", url) is not None

    def detect_html(self, html: str) -> bool:
        return "data-message-author-role" in html

    async def parse(self, page: Page, url: str) -> Conversation:
        try:
            await page.wait_for_selector(MESSAGE_SELECTOR, timeout=WAIT_FOR_MESSAGES_MS)
        except PlaywrightTimeout:
            await self._log_failure(page, url)
            raise ExtractionError(
                "No messages found on the ChatGPT share page. The link may be "
                "expired, private, or the page structure may have changed."
            )
        messages: list[Message] = []
        for element in await page.locator(MESSAGE_SELECTOR).all():
            raw_role = await element.get_attribute("data-message-author-role")
            role: Role = raw_role if raw_role in VALID_ROLES else "assistant"
            message = await self._message_from_element(element, role)
            if message.content:
                messages.append(message)
        if not messages:
            await self._log_failure(page, url)
            raise ExtractionError("The ChatGPT share page contained no message text.")
        return Conversation(
            platform=self.platform,
            title=await self._title(page),
            source_url=url,
            messages=messages,
        )
