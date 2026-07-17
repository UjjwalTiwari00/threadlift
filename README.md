# ThreadLift

Paste a ChatGPT, Claude, or Gemini **share link** and get the conversation
back as clean, normalized JSON — plus a simple web UI to browse and download
it. Built with FastAPI + Playwright, designed to deploy on Render as a
single Docker web service.

## How it works

```
POST /extract {url}
        │
        ▼
Platform Detector   (URL pattern → which extractor)
        │
        ▼
Browser Manager     (one shared headless Chromium, fresh context per request)
        │
        ▼
Platform Extractor  (chatgpt / claude / gemini / generic fallback)
        │
        ▼
Normalized JSON     (same shape regardless of source platform)
```

Every extractor implements the same interface
([app/extractors/base.py](app/extractors/base.py)) and returns the same
`Conversation` model ([app/models.py](app/models.py)):

```json
{
  "platform": "chatgpt",
  "title": "Invoice Parser",
  "source_url": "https://chatgpt.com/share/...",
  "extracted_at": "2026-07-17T12:00:00Z",
  "messages": [
    {"role": "user", "content": "Build a parser", "code_blocks": []},
    {"role": "assistant", "content": "Let's start...",
     "code_blocks": [{"language": "python", "content": "..."}]}
  ]
}
```

Adding a new platform = one new file in `app/extractors/` + one line in
`app/detector.py`.

## Run locally

Requires Python 3.11+.

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows (use source .venv/bin/activate on Linux/macOS)
pip install -r requirements-dev.txt
playwright install chromium   # downloads the browser locally
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 — or call the API directly:

```bash
curl -X POST http://127.0.0.1:8000/extract \
     -H "Content-Type: application/json" \
     -d "{\"url\": \"https://chatgpt.com/share/...\"}"

# fallback for bot-protected pages (e.g. claude.ai): upload saved HTML
curl -X POST http://127.0.0.1:8000/extract-html -F "file=@saved-page.html"
```

> **Windows note:** don't use `uvicorn --reload` — it forces an event loop
> that can't spawn subprocesses, so Playwright fails with
> `NotImplementedError`. Restart manually instead. Linux/Docker unaffected.

## Run tests

```bash
pytest
```

Detector tests always run. Extractor tests run against saved share pages in
`tests/fixtures/` and are skipped until you capture fixtures — see
[tests/fixtures/README.md](tests/fixtures/README.md).

## Deploy to Render

1. Push this folder to a GitHub repo.
2. In Render: **New → Blueprint**, pick the repo. Render reads
   [render.yaml](render.yaml) and builds the [Dockerfile](Dockerfile)
   (based on the official Playwright image, so Chromium and its system
   dependencies are already included).
3. Done — no environment variables needed for v1.

### Render caveats to know

- **Free tier (512MB RAM)** is tight for Chromium. The app caps concurrent
  extractions at 2 (`MAX_CONCURRENT_PAGES` in
  [app/browser.py](app/browser.py)); drop it to 1 or upgrade to the Starter
  plan if you see out-of-memory restarts.
- Free services **spin down after ~15 idle minutes**; the first request
  after that takes 30–60s.
- The Playwright pip version in `requirements.txt` **must match** the Docker
  base image tag — upgrade both together.

## Maintenance notes

- Platforms redesign their pages; when an extractor breaks, refresh its
  selectors and the matching fixture. ChatGPT's
  `data-message-author-role` attribute has been the most stable anchor;
  Claude's DOM changes most often.
- Some platforms bot-protect even headless browsers. **claude.ai does**
  (Cloudflare "Just a moment…" challenge blocks both headless Chromium and
  Firefox — verified 2026-07). The escape hatch is `POST /extract-html`:
  the user opens the link in their own browser, saves the rendered HTML,
  and uploads it; extractors are picked by DOM fingerprint
  (`detect_html`) and parse the file via `page.set_content()` with
  JavaScript disabled.

## Roadmap

- [x] Upload-HTML fallback for bot-protected pages (`POST /extract-html`)
- [ ] AI summary endpoint (Claude API) on top of the normalized JSON
- [ ] Export to Markdown
- [ ] More platforms (DeepSeek, Perplexity, ...)

## Not yet handled (be aware)

- **SSRF**: the service fetches any URL a user submits. Before exposing it
  publicly beyond a demo, restrict extraction to an allowlist of known
  share-link domains.
- No rate limiting or auth on `/extract`.
