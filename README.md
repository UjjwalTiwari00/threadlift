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
