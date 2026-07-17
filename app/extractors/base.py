"""Extractor interface and shared parsing helpers.

Each platform extractor implements:
  detect(url)        -> does this extractor handle the URL?
  detect_html(html)  -> does this look like this platform's page? (for uploads)
  extract(page, url) -> navigate and parse; returns a normalized Conversation

extract() is split into _goto() + parse() so uploaded/saved HTML can be
loaded with page.set_content() and parsed directly, without the network.
Tests use the same path.
"""

import asyncio
import logging
import os
from abc import ABC, abstractmethod

from playwright.async_api import Locator, Page

from app.models import CodeBlock, Conversation, Message, Role

# Overridable per deployment: slow instances (Render free tier, 0.1 CPU)
# can need far longer than a dev laptop to render an SPA.
WAIT_FOR_MESSAGES_MS = int(os.environ.get("EXTRACT_WAIT_MS", "15000"))

logger = logging.getLogger("threadlift.extractor")
SETTLE_INTERVAL_MS = 400
SETTLE_STABLE_CHECKS = 2
SETTLE_MAX_WAIT_MS = 8_000


class ExtractionError(Exception):
    """Raised when a page loads but no conversation can be found on it."""


class BaseExtractor(ABC):
    platform: str = "generic"

    @abstractmethod
    def detect(self, url: str) -> bool: ...

    def detect_html(self, html: str) -> bool:
        return False

    @abstractmethod
    async def parse(self, page: Page, url: str) -> Conversation: ...

    async def extract(self, page: Page, url: str) -> Conversation:
        await self._goto(page, url)
        return await self.parse(page, url)

    async def _goto(self, page: Page, url: str) -> None:
        await page.goto(url, wait_until="domcontentloaded")

    async def _log_failure(self, page: Page, url: str) -> None:
        """Snapshot what the page actually showed; invaluable for prod-only bugs."""
        try:
            title = await page.title()
            body = (await page.locator("body").inner_text())[:300]
        except Exception:
            title, body = "<unavailable>", "<unavailable>"
        logger.warning(
            "extraction failed: platform=%s url=%s page_title=%r body_snippet=%r",
            self.platform,
            url,
            title,
            body,
        )

    async def _title(self, page: Page) -> str:
        og = page.locator('meta[property="og:title"]')
        if await og.count():
            content = await og.first.get_attribute("content")
            if content and content.strip():
                return content.strip()
        return (await page.title()).strip()

    async def _message_from_element(
        self,
        element: Locator,
        role: Role,
        content_selector: str | None = None,
    ) -> Message:
        # content_selector narrows to the actual message text when the turn
        # element also contains UI chrome (labels like "You said", buttons).
        content = ""
        if content_selector:
            inner = element.locator(content_selector)
            texts = [(await node.inner_text()).strip() for node in await inner.all()]
            content = "\n\n".join(t for t in texts if t)
        if not content:
            content = (await element.inner_text()).strip()
        code_blocks: list[CodeBlock] = []
        for pre in await element.locator("pre").all():
            code = pre.locator("code").first
            language = ""
            if await code.count():
                css_classes = (await code.get_attribute("class")) or ""
                for part in css_classes.split():
                    if part.startswith("language-"):
                        language = part.removeprefix("language-")
                        break
                text = await code.inner_text()
            else:
                text = await pre.inner_text()
            if text.strip():
                code_blocks.append(CodeBlock(language=language, content=text.strip()))
        return Message(role=role, content=content, code_blocks=code_blocks)

    async def _extract_role_pairs(
        self,
        page: Page,
        user_selector: str,
        assistant_selector: str,
        timeout_ms: int = WAIT_FOR_MESSAGES_MS,
        user_content_selector: str | None = None,
        assistant_content_selector: str | None = None,
    ) -> list[Message]:
        """Collect messages, in document order, from two role-specific selectors."""
        combined = f"{user_selector}, {assistant_selector}"
        await page.wait_for_selector(combined, timeout=timeout_ms)
        messages: list[Message] = []
        for element in await page.locator(combined).all():
            is_user = await element.evaluate(
                "(el, sel) => el.matches(sel)", user_selector
            )
            role: Role = "user" if is_user else "assistant"
            message = await self._message_from_element(
                element,
                role,
                user_content_selector if is_user else assistant_content_selector,
            )
            if message.content:
                messages.append(message)
        return messages
