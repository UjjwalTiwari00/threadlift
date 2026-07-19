"""Extractor for ChatGPT share links (chatgpt.com/share/... or chat.openai.com/share/...).

Primary path: the share page embeds the entire conversation in the initial
HTML as a React Router "turbo-stream" payload inside
window.__reactRouterContext.streamController.enqueue("...") script chunks.
We decode that payload directly, so extraction works even when ChatGPT's
client-side app refuses to render the messages (which it does for
datacenter IPs + headless browsers — it shows the logged-out shell
instead, so DOM-based extraction fails on hosts like Render).

Fallback path: wait for [data-message-author-role] in the rendered DOM.
Still needed for uploaded pages saved *after* client-side rendering, where
the stream scripts may be gone but the message DOM is present.
"""

import json
import logging
import re
from typing import Any

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from app.extractors.base import WAIT_FOR_MESSAGES_MS, BaseExtractor, ExtractionError
from app.models import CodeBlock, Conversation, Message, Role

logger = logging.getLogger("threadlift.extractor")

MESSAGE_SELECTOR = "[data-message-author-role]"
VALID_ROLES = ("user", "assistant", "system")

_ENQUEUE_RE = re.compile(r'streamController\.enqueue\("((?:[^"\\]|\\.)*)"\)')
_FENCE_RE = re.compile(r"```([\w#+.-]*)[ \t]*\n(.*?)```", re.DOTALL)

# turbo-stream can encode reference cycles; a depth cap keeps the decoder
# total. Real conversation payloads are nowhere near this deep.
_MAX_DECODE_DEPTH = 64


def _decode_ref(values: list, ref: Any, depth: int = 0) -> Any:
    """Resolve one turbo-stream reference into a plain Python value.

    The payload is a flat JSON array. Objects are encoded as
    {"_<key index>": <value index>} and arrays hold value indices; scalars
    are stored literally. Negative indices are sentinels (undefined, NaN,
    +/-Infinity) — we map them all to None.
    """
    if depth > _MAX_DECODE_DEPTH:
        return None
    if not isinstance(ref, int) or not 0 <= ref < len(values):
        return None
    node = values[ref]
    if isinstance(node, dict):
        out = {}
        for key_ref, value_ref in node.items():
            if not key_ref.startswith("_"):
                # Not flat-encoded; treat as a literal object.
                return node
            key = _decode_ref(values, int(key_ref[1:]), depth + 1)
            if isinstance(key, str):
                out[key] = _decode_ref(values, value_ref, depth + 1)
        return out
    if isinstance(node, list):
        # Typed values (Dates, Maps, ...) are tagged arrays; decoding their
        # elements naively is fine — we only consume plain data.
        return [
            _decode_ref(values, item, depth + 1) if isinstance(item, int) else item
            for item in node
        ]
    return node


def _decode_stream_payload(html: str) -> Any:
    """Find and decode the root turbo-stream chunk in the page HTML."""
    for match in _ENQUEUE_RE.finditer(html):
        try:
            chunk = json.loads(f'"{match.group(1)}"')  # unescape the JS literal
        except ValueError:
            continue
        # Later chunks are deferred-promise patches like 'P290:[{}]';
        # only the root chunk is a bare JSON array.
        if not chunk.lstrip().startswith("["):
            continue
        try:
            values = json.loads(chunk)
        except ValueError:
            continue
        if isinstance(values, list) and values:
            return _decode_ref(values, 0)
    return None


def _code_blocks_from_markdown(text: str) -> list[CodeBlock]:
    return [
        CodeBlock(language=language, content=body.strip())
        for language, body in _FENCE_RE.findall(text)
        if body.strip()
    ]


class ChatGPTExtractor(BaseExtractor):
    platform = "chatgpt"

    def detect(self, url: str) -> bool:
        return re.search(r"(chatgpt\.com|chat\.openai\.com)/share/", url) is not None

    def detect_html(self, html: str) -> bool:
        # Rendered DOM marker, or the embedded payload in raw page source.
        return "data-message-author-role" in html or (
            "streamController.enqueue" in html and "linear_conversation" in html
        )

    async def extract(self, page: Page, url: str) -> Conversation:
        response = await page.goto(url, wait_until="domcontentloaded")
        # Parse the raw network response, not the live DOM: hydration can
        # relocate or consume the stream script tags after load.
        if response is not None:
            conversation = self._from_embedded(await response.text(), url)
            if conversation is not None:
                return conversation
            logger.info("chatgpt: no embedded payload in %s; trying rendered DOM", url)
        return await self.parse(page, url)

    async def parse(self, page: Page, url: str) -> Conversation:
        # Uploaded raw HTML (and fixtures) carry the embedded payload too.
        conversation = self._from_embedded(await page.content(), url)
        if conversation is not None:
            return conversation
        return await self._parse_dom(page, url)

    def _from_embedded(self, html: str, url: str) -> Conversation | None:
        try:
            return self._conversation_from_payload(html, url)
        except Exception:
            # A malformed payload must not kill the request while the DOM
            # fallback can still succeed.
            logger.exception("chatgpt: embedded payload decode failed for %s", url)
            return None

    def _conversation_from_payload(self, html: str, url: str) -> Conversation | None:
        root = _decode_stream_payload(html)
        if not isinstance(root, dict):
            return None
        loader_data = root.get("loaderData")
        if not isinstance(loader_data, dict):
            return None
        share = next(
            (
                route_data
                for route_id, route_data in loader_data.items()
                if "share" in route_id and isinstance(route_data, dict)
            ),
            None,
        )
        if share is None:
            return None
        server_response = share.get("serverResponse")
        if not isinstance(server_response, dict):
            return None
        data = server_response.get("data")
        if not isinstance(data, dict):
            return None

        nodes = data.get("linear_conversation")
        if not isinstance(nodes, list) or not nodes:
            mapping = data.get("mapping")
            nodes = list(mapping.values()) if isinstance(mapping, dict) else []

        messages: list[Message] = []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            raw = node.get("message")
            if not isinstance(raw, dict):
                continue
            raw_role = (raw.get("author") or {}).get("role")
            if raw_role not in VALID_ROLES:
                continue
            metadata = raw.get("metadata") or {}
            if metadata.get("is_visually_hidden_from_conversation"):
                continue
            parts = (raw.get("content") or {}).get("parts") or []
            content = "\n\n".join(
                part.strip() for part in parts if isinstance(part, str) and part.strip()
            )
            if not content:
                continue
            role: Role = raw_role
            messages.append(
                Message(
                    role=role,
                    content=content,
                    code_blocks=_code_blocks_from_markdown(content),
                )
            )
        if not messages:
            return None
        return Conversation(
            platform=self.platform,
            title=(data.get("title") or "").strip(),
            source_url=url,
            messages=messages,
        )

    async def _parse_dom(self, page: Page, url: str) -> Conversation:
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
