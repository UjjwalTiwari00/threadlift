"""Extractor interface and shared parsing helpers.

Each platform extractor implements:
  detect(url)        -> does this extractor handle the URL?
  detect_html(html)  -> does this look like this platform's page? (for uploads)
  extract(page, url) -> navigate and parse; returns a normalized Conversation

extract() is split into _goto() + parse() so uploaded/saved HTML can be
loaded with page.set_content() and parsed directly, without the network.
Tests use the same path.
"""

from abc import ABC, abstractmethod

from playwright.async_api import Locator, Page

from app.models import CodeBlock, Conversation, Message, Role

WAIT_FOR_MESSAGES_MS = 15_000


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

    async def _title(self, page: Page) -> str:
        og = page.locator('meta[property="og:title"]')
        if await og.count():
            content = await og.first.get_attribute("content")
            if content and content.strip():
                return content.strip()
        return (await page.title()).strip()

    async def _message_from_element(self, element: Locator, role: Role) -> Message:
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
            message = await self._message_from_element(element, role)
            if message.content:
                messages.append(message)
        return messages
