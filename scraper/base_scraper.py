"""Base scraper: rate-limiter, retry, robots.txt respect, HTML cache."""
import hashlib
import random
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from config.settings import SCRAPER_MIN_DELAY, SCRAPER_MAX_DELAY, SCRAPE_CACHE_DIR, SCRAPE_CACHE_TTL_DAYS
from utils.logger import get_logger

log = get_logger(__name__)

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
]

# Headers that closely mimic a real browser navigation request
_BROWSER_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}


def _is_retriable(exc: BaseException) -> bool:
    """Only retry on transient server errors or rate-limiting; not on 403/404."""
    if isinstance(exc, requests.HTTPError):
        code = exc.response.status_code if exc.response is not None else 0
        return code in (429, 500, 502, 503, 504)
    return True  # connection errors, timeouts, etc. are retriable


class BaseScraper:
    def __init__(self, respect_robots: bool = True, use_cache: bool = True):
        self.respect_robots = respect_robots
        self.use_cache = use_cache
        self._robots_cache: dict[str, RobotFileParser] = {}
        self._session = requests.Session()

    def _get_ua(self) -> str:
        return random.choice(_USER_AGENTS)

    def _cache_path(self, url: str) -> Path:
        key = hashlib.sha256(url.encode()).hexdigest()
        return SCRAPE_CACHE_DIR / f"{key}.html"

    def _is_cache_valid(self, path: Path) -> bool:
        if not path.exists():
            return False
        age_days = (time.time() - path.stat().st_mtime) / 86400
        return age_days < SCRAPE_CACHE_TTL_DAYS

    def _read_cache(self, url: str) -> Optional[str]:
        if not self.use_cache:
            return None
        p = self._cache_path(url)
        if self._is_cache_valid(p):
            log.debug("Cache hit: %s", url)
            return p.read_text(encoding="utf-8", errors="replace")
        return None

    def _write_cache(self, url: str, html: str) -> None:
        if not self.use_cache:
            return
        p = self._cache_path(url)
        p.write_text(html, encoding="utf-8")

    def _can_fetch(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        if base not in self._robots_cache:
            rp = RobotFileParser()
            try:
                # Use our requests session (with browser headers) instead of
                # urllib, which gets different/compressed responses that
                # RobotFileParser.read() fails to parse, returning False for all URLs.
                robots_url = f"{base}/robots.txt"
                r = self._session.get(
                    robots_url,
                    headers={**_BROWSER_HEADERS, "User-Agent": self._get_ua()},
                    timeout=10,
                )
                if r.status_code == 200:
                    rp.set_url(robots_url)
                    rp.parse(r.text.splitlines())
                elif r.status_code in (401, 403):
                    rp.disallow_all = True
                # 404 / other → allow all (rp stays empty → can_fetch returns True)
                self._robots_cache[base] = rp
            except Exception:
                self._robots_cache[base] = None
        rp = self._robots_cache.get(base)
        if rp is None:
            return True
        return rp.can_fetch("*", url)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception(_is_retriable),
        reraise=True,
    )
    def _fetch_with_requests(self, url: str) -> str:
        """Inner requests fetch — retried only on transient errors."""
        delay = random.uniform(SCRAPER_MIN_DELAY, SCRAPER_MAX_DELAY)
        time.sleep(delay)
        headers = {**_BROWSER_HEADERS, "User-Agent": self._get_ua()}
        resp = self._session.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        return resp.text

    def _fetch_html(self, url: str) -> Optional[str]:
        """Fetch URL with cache, requests (retry on transient errors), then Playwright fallback."""
        cached = self._read_cache(url)
        if cached:
            return cached

        if not self._can_fetch(url):
            log.warning("robots.txt disallows: %s", url)
            return None

        html: Optional[str] = None
        try:
            html = self._fetch_with_requests(url)
            log.info("Fetched via requests: %s (%d bytes)", url, len(html))
        except Exception as exc:
            status = ""
            if isinstance(exc, requests.HTTPError) and exc.response is not None:
                status = f" HTTP {exc.response.status_code}"
            log.warning("requests failed%s for %s: %s — trying Playwright", status, url, exc)
            from scraper.playwright_fallback import fetch_with_playwright
            html = fetch_with_playwright(url)
            if html:
                log.info("Fetched via Playwright: %s (%d bytes)", url, len(html))

        if html:
            self._write_cache(url, html)
        return html

    def get_soup(self, url: str) -> Optional[BeautifulSoup]:
        """Fetch URL and return BeautifulSoup object."""
        html = self._fetch_html(url)
        if html is None:
            return None
        return BeautifulSoup(html, "lxml")

    def scrape(self, url: str, **kwargs) -> list[dict]:
        """Override in subclasses. Returns list of chunk dicts."""
        raise NotImplementedError
