from app.detector import get_extractor


def test_chatgpt_urls():
    assert get_extractor("https://chatgpt.com/share/abc-123").platform == "chatgpt"
    assert get_extractor("https://chat.openai.com/share/abc").platform == "chatgpt"


def test_claude_urls():
    assert get_extractor("https://claude.ai/share/abc-123").platform == "claude"


def test_gemini_urls():
    assert get_extractor("https://gemini.google.com/share/abc").platform == "gemini"
    assert get_extractor("https://g.co/gemini/share/abc").platform == "gemini"


def test_unknown_urls_fall_back_to_generic():
    assert get_extractor("https://example.com/some-chat").platform == "generic"


def test_html_fingerprints():
    from app.detector import get_extractor_for_html

    chatgpt = '<div data-message-author-role="user">hi</div>'
    claude = '<div data-testid="user-message">hi</div>'
    gemini = "<user-query>hi</user-query><model-response>yo</model-response>"
    assert get_extractor_for_html(chatgpt).platform == "chatgpt"
    assert get_extractor_for_html(claude).platform == "claude"
    assert get_extractor_for_html(gemini).platform == "gemini"
    assert get_extractor_for_html("<html><p>plain</p></html>").platform == "generic"
