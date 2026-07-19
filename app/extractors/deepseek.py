"""Extractor for DeepSeek share links (chat.deepseek.com/share/<id>).

The share page sits behind a "Human Verification" JS challenge. It
auto-passes in ~5s in a browser that doesn't advertise automation
(requires --disable-blink-features=AutomationControlled, see browser.py),
after which the app loads the conversation from a clean JSON API:

    GET /api/v0/share/content?share_id=<id>
    -> data.biz_data: {title, messages: [{role: USER|ASSISTANT,
                       fragments: [{type: REQUEST|RESPONSE, content}]}]}

extract() awaits that API response and parses it directly — no DOM
scraping, so styling changes can't break it. parse() (upload fallback)
reads the rendered DOM: every turn is .ds-message and assistant turns
contain .ds-assistant-message-main-content.
"""

import re

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from app.extractors.base import (
    WAIT_FOR_MESSAGES_MS,
    BaseExtractor,
    ExtractionError,
    code_blocks_from_markdown,
)
from app.models import Conversation, Message

SHARE_API_MARKER = "/api/v0/share/content"
ROLE_MAP = {"USER": "user", "ASSISTANT": "assistant", "SYSTEM": "system"}
TEXT_FRAGMENT_TYPES = ("REQUEST", "RESPONSE")

USER_SELECTOR = ".ds-message:not(:has(.ds-assistant-message-main-content))"
ASSISTANT_SELECTOR = ".ds-message:has(.ds-assistant-message-main-content)"
ASSISTANT_CONTENT_SELECTOR = ".ds-assistant-message-main-content"


class DeepSeekExtractor(BaseExtractor):
    platform = "deepseek"

    def detect(self, url: str) -> bool:
        return re.search(r"chat\.deepseek\.com/share/", url) is not None

    def detect_html(self, html: str) -> bool:
        return "ds-assistant-message-main-content" in html

    async def extract(self, page: Page, url: str) -> Conversation:
        # The WAF sometimes answers with an empty 202 instead of the
        # challenge page (observed intermittently); a fresh navigation
        # usually gets the real flow, so split the wait budget over two
        # attempts instead of spending it all on one.
        attempt_timeout = max(WAIT_FOR_MESSAGES_MS // 2, 10_000)
        response = None
        for attempt in range(2):
            try:
                async with page.expect_response(
                    lambda r: SHARE_API_MARKER in r.url and r.ok,
                    timeout=attempt_timeout,
                ) as response_info:
                    await page.goto(url, wait_until="domcontentloaded")
                response = await response_info.value
                break
            except PlaywrightTimeout:
                if attempt == 1:
                    await self._log_failure(page, url)
                    raise ExtractionError(
                        "DeepSeek never served the shared conversation. The "
                        "link may be expired, or the human-verification "
                        "challenge did not pass."
                    )
        conversation = self.conversation_from_payload(await response.json(), url)
        if conversation is None:
            raise ExtractionError(
                "The DeepSeek share API returned no messages. The link may be "
                "expired or private."
            )
        return conversation

    def conversation_from_payload(self, payload: dict, url: str) -> Conversation | None:
        biz_data = ((payload.get("data") or {}).get("biz_data")) or {}
        messages: list[Message] = []
        for raw in biz_data.get("messages") or []:
            role = ROLE_MAP.get(raw.get("role"))
            if role is None:
                continue
            # Fragments also carry THINK/search stages; only REQUEST and
            # RESPONSE hold the visible conversation text.
            parts = [
                (fragment.get("content") or "").strip()
                for fragment in raw.get("fragments") or []
                if fragment.get("type") in TEXT_FRAGMENT_TYPES
            ]
            content = "\n\n".join(part for part in parts if part)
            if not content:
                continue
            messages.append(
                Message(
                    role=role,
                    content=content,
                    code_blocks=code_blocks_from_markdown(content),
                )
            )
        if not messages:
            return None
        return Conversation(
            platform=self.platform,
            title=(biz_data.get("title") or "").strip(),
            source_url=url,
            messages=messages,
        )

    async def parse(self, page: Page, url: str) -> Conversation:
        try:
            messages = await self._extract_role_pairs(
                page,
                USER_SELECTOR,
                ASSISTANT_SELECTOR,
                assistant_content_selector=ASSISTANT_CONTENT_SELECTOR,
            )
        except PlaywrightTimeout:
            await self._log_failure(page, url)
            raise ExtractionError(
                "No messages found on the DeepSeek share page. The link may "
                "be expired or private, or the page structure may have changed."
            )
        if not messages:
            await self._log_failure(page, url)
            raise ExtractionError("The DeepSeek share page contained no message text.")
        return Conversation(
            platform=self.platform,
            title=await self._title(page),
            source_url=url,
            messages=messages,
        )
