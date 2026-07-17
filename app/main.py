from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from playwright.async_api import TimeoutError as PlaywrightTimeout
from pydantic import BaseModel, HttpUrl

from app.browser import browser_manager
from app.detector import get_extractor, get_extractor_for_html
from app.extractors.base import ExtractionError
from app.models import Conversation


@asynccontextmanager
async def lifespan(_: FastAPI):
    await browser_manager.start()
    yield
    await browser_manager.stop()


app = FastAPI(title="ThreadLift", lifespan=lifespan)

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


class ExtractRequest(BaseModel):
    url: HttpUrl


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/extract", response_model=Conversation)
async def extract(body: ExtractRequest) -> Conversation:
    url = str(body.url)
    extractor = get_extractor(url)
    try:
        async with browser_manager.page() as page:
            return await extractor.extract(page, url)
    except ExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except PlaywrightTimeout:
        raise HTTPException(
            status_code=504,
            detail="The page took too long to load. Try again, or check that "
            "the link opens in a normal browser.",
        )


MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@app.post("/extract-html", response_model=Conversation)
async def extract_html(file: UploadFile = File(...)) -> Conversation:
    """Fallback for bot-protected pages: parse HTML the user saved themselves."""
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10MB).")
    html = raw.decode("utf-8", errors="replace")
    extractor = get_extractor_for_html(html)
    try:
        async with browser_manager.page(js_enabled=False) as page:
            await page.set_content(html, wait_until="domcontentloaded")
            return await extractor.parse(page, f"upload://{file.filename}")
    except ExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
