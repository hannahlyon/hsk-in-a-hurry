"""Playwright fallback for JS-rendered pages."""
from typing import Optional
from utils.logger import get_logger

log = get_logger(__name__)


def fetch_with_playwright(url: str, wait_selector: Optional[str] = None,
                           timeout: int = 15000) -> Optional[str]:
    """
    Fetch a JS-rendered page using Playwright (Chromium).
    Returns HTML string or None on failure.
    Requires: playwright install chromium
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.error("Playwright not installed. Run: playwright install chromium")
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers({
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            })
            page.goto(url, timeout=timeout)
            if wait_selector:
                page.wait_for_selector(wait_selector, timeout=timeout)
            else:
                page.wait_for_load_state("networkidle", timeout=timeout)
            html = page.content()
            browser.close()
            log.info("Playwright fetched: %s (%d bytes)", url, len(html))
            return html
    except Exception as exc:
        log.error("Playwright error for %s: %s", url, exc)
        return None
