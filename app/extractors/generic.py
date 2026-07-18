"""Best-effort fallback extractor for unrecognized chat pages.

Tries a list of role-selector patterns seen across chat UIs; if none match,
returns the page's main text as a single message so the user still gets
something usable.
"""

from playwright.async_api import Page

from app.extractors.base import BaseExtractor, ExtractionError
from app.models import Conversation, Message

CANDIDATE_PAIRS = [
    ('[data-role="user"]', '[data-role="assistant"]'),
    (".message.user", ".message.assistant"),
    ('[data-message-author-role="user"]', '[data-message-author-role="assistant"]'),
    ('[data-testid="user-message"]', ".font-claude-message"),
    ("user-query", "response-container, model-response"),
]

PER_PATTERN_TIMEOUT_MS = 3_000


class GenericExtractor(BaseExtractor):
    platform = "generic"

    def detect(self, url: str) -> bool:
        return True

    def detect_html(self, html: str) -> bool:
        return True

    async def parse(self, page: Page, url: str) -> Conversation:
        title = await self._title(page)
        for user_selector, assistant_selector in CANDIDATE_PAIRS:
            try:
                messages = await self._extract_role_pairs(
                    page,
                    user_selector,
                    assistant_selector,
                    timeout_ms=PER_PATTERN_TIMEOUT_MS,
                )
            except Exception:
                continue
            if messages:
                return Conversation(
                    platform=self.platform,
                    title=title,
                    source_url=url,
                    messages=messages,
                )

        # Last resort: the whole visible page as one message.
        container = page.locator("main")
        if not await container.count():
            container = page.locator("body")
        text = (await container.first.inner_text()).strip()
        if not text:
            await self._log_failure(page, url)
            raise ExtractionError(
                "Could not find any conversation content on this page."
            )
        return Conversation(
            platform=self.platform,
            title=title,
            source_url=url,
            messages=[Message(role="assistant", content=text)],
        )
