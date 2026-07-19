"""Maps a URL to the extractor that handles it."""

from app.extractors.base import BaseExtractor
from app.extractors.chatgpt import ChatGPTExtractor
from app.extractors.claude import ClaudeExtractor
from app.extractors.deepseek import DeepSeekExtractor
from app.extractors.gemini import GeminiExtractor
from app.extractors.generic import GenericExtractor
from app.extractors.kimi import KimiExtractor

EXTRACTORS: list[BaseExtractor] = [
    ChatGPTExtractor(),
    ClaudeExtractor(),
    GeminiExtractor(),
    KimiExtractor(),
    DeepSeekExtractor(),
]

_GENERIC = GenericExtractor()


def get_extractor(url: str) -> BaseExtractor:
    for extractor in EXTRACTORS:
        if extractor.detect(url):
            return extractor
    return _GENERIC


def get_extractor_for_html(html: str) -> BaseExtractor:
    """Pick an extractor for uploaded HTML by DOM fingerprint (no URL available)."""
    for extractor in EXTRACTORS:
        if extractor.detect_html(html):
            return extractor
    return _GENERIC
