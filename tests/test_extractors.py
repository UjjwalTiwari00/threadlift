"""Fixture-based extractor tests.

Each test loads a saved share page from tests/fixtures/ into a real
(offline) browser page and runs the extractor's parse() on it. Tests are
skipped when the fixture is missing — see tests/fixtures/README.md for how
to capture fixtures.
"""

from pathlib import Path

import pytest
from playwright.async_api import async_playwright

import json

from app.extractors.chatgpt import ChatGPTExtractor
from app.extractors.claude import ClaudeExtractor
from app.extractors.deepseek import DeepSeekExtractor
from app.extractors.gemini import GeminiExtractor
from app.extractors.kimi import KimiExtractor

FIXTURES = Path(__file__).parent / "fixtures"

CASES = [
    ("chatgpt.html", ChatGPTExtractor(), "https://chatgpt.com/share/fixture"),
    ("claude.html", ClaudeExtractor(), "https://claude.ai/share/fixture"),
    ("gemini.html", GeminiExtractor(), "https://gemini.google.com/share/fixture"),
    ("kimi.html", KimiExtractor(), "https://www.kimi.com/share/fixture"),
    ("deepseek.html", DeepSeekExtractor(), "https://chat.deepseek.com/share/fixture"),
]


async def parse_fixture(filename, extractor, url):
    fixture = FIXTURES / filename
    if not fixture.exists():
        pytest.skip(f"fixture {filename} not captured yet")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_content(
                fixture.read_text(encoding="utf-8"), wait_until="domcontentloaded"
            )
            return await extractor.parse(page, url)
        finally:
            await browser.close()


@pytest.mark.parametrize(
    "filename,extractor,url", CASES, ids=[c[1].platform for c in CASES]
)
async def test_extractor_parses_fixture(filename, extractor, url):
    conversation = await parse_fixture(filename, extractor, url)

    assert conversation.platform == extractor.platform
    assert conversation.messages, "extractor returned no messages"
    assert any(m.role == "user" for m in conversation.messages)
    assert any(m.role == "assistant" for m in conversation.messages)


async def test_chatgpt_fixture_embedded_payload():
    # chatgpt.html is raw page source (not rendered DOM): it exercises the
    # embedded turbo-stream path, which is what production relies on.
    conversation = await parse_fixture(
        "chatgpt.html", ChatGPTExtractor(), "https://chatgpt.com/share/fixture"
    )

    assert conversation.title == "Inner Join Syntax"
    user_messages = [m for m in conversation.messages if m.role == "user"]
    assert user_messages[0].content == "innner join of two table syntax"
    assistant_messages = [m for m in conversation.messages if m.role == "assistant"]
    assert assistant_messages[0].code_blocks
    assert assistant_messages[0].code_blocks[0].language == "sql"
    assert "INNER JOIN" in assistant_messages[0].code_blocks[0].content


def test_deepseek_api_payload():
    # The live path parses the share API response, not the DOM.
    fixture = FIXTURES / "deepseek_api.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))

    conversation = DeepSeekExtractor().conversation_from_payload(
        payload, "https://chat.deepseek.com/share/fixture"
    )

    assert conversation is not None
    assert conversation.title == "Shared Conversation"
    assert len(conversation.messages) == 6
    user_messages = [m for m in conversation.messages if m.role == "user"]
    assert user_messages[0].content == "hii"
    assistant_messages = [m for m in conversation.messages if m.role == "assistant"]
    assert assistant_messages[0].content.startswith("Hello!")


async def test_kimi_fixture_content_is_clean():
    conversation = await parse_fixture(
        "kimi.html", KimiExtractor(), "https://www.kimi.com/share/fixture"
    )

    assert conversation.title == "Hacking Discount Attempt"
    user_messages = [m for m in conversation.messages if m.role == "user"]
    assert user_messages[0].content == "sudo slash --price=0.99"
    assistant_messages = [m for m in conversation.messages if m.role == "assistant"]
    # content selector must exclude avatar/card chrome around the markdown
    assert assistant_messages[0].content.startswith("lmao nice try hacker")


async def test_gemini_fixture_content_is_clean():
    conversation = await parse_fixture(
        "gemini.html", GeminiExtractor(), "https://gemini.google.com/share/fixture"
    )

    assert conversation.title == "Greeting and Offer of Assistance"
    user_messages = [m for m in conversation.messages if m.role == "user"]
    assert user_messages[0].content == "hi"
    # the visually-hidden screen-reader label must not leak into content
    assert all("You said" not in m.content for m in user_messages)
