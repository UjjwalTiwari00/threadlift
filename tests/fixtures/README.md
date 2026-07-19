# Test fixtures

Extractor tests run against saved copies of real share pages, so they work
offline and tell you exactly which extractor broke after a platform redesign.

## How to capture a fixture

1. Open the share link in a normal browser and let it fully render.
2. Open DevTools → Console and run:
   ```js
   copy(document.documentElement.outerHTML)
   ```
   (this copies the *rendered* DOM — "Save page as…" often saves the
   pre-render shell, which is useless for client-rendered pages)
3. Paste into a new file here:
   - `chatgpt.html`
   - `claude.html`
   - `gemini.html`

Tests for missing fixtures are skipped, not failed.

Exception — `chatgpt.html` should be the **raw page source** (view-source /
`curl`), not the rendered DOM: ChatGPT embeds the conversation as JSON in
the initial HTML and the extractor parses that directly. The rendered-DOM
selector path is only a fallback there.

Tip: use a throwaway conversation for fixtures — these files get committed.
