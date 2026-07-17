"""Fixture-based extractor tests.

Each test loads a saved share page from tests/fixtures/ into a real
(offline) browser page and runs the extractor's parse() on it. Tests are
skipped when the fixture is missing — see tests/fixtures/README.md for how
to capture fixtures.
"""

from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from app.extractors.chatgpt import ChatGPTExtractor
from app.extractors.claude import ClaudeExtractor
from app.extractors.gemini import GeminiExtractor

FIXTURES = Path(__file__).parent / "fixtures"

CASES = [
    ("chatgpt.html", ChatGPTExtractor(), "https://chatgpt.com/share/fixture"),
    ("claude.html", ClaudeExtractor(), "https://claude.ai/share/fixture"),
    ("gemini.html", GeminiExtractor(), "https://gemini.google.com/share/fixture"),
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


async def test_gemini_fixture_content_is_clean():
    conversation = await parse_fixture(
        "gemini.html", GeminiExtractor(), "https://gemini.google.com/share/fixture"
    )

    assert conversation.title == "Greeting and Offer of Assistance"
    user_messages = [m for m in conversation.messages if m.role == "user"]
    assert user_messages[0].content == "hi"
    # the visually-hidden screen-reader label must not leak into content
    assert all("You said" not in m.content for m in user_messages)
