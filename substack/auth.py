"""Cookie loading and requests.Session builder for Substack."""
import requests
from typing import Optional
from utils.logger import get_logger

log = get_logger(__name__)


class SubstackAuthError(Exception):
    """Raised on 401/403 from Substack API."""


def build_session(cookie_string: str) -> requests.Session:
    """
    Build an authenticated requests.Session from a Substack cookie string.

    The cookie_string should be the raw value of the 'Cookie' header
    copied from browser DevTools after logging into Substack.
    """
    if not cookie_string or not cookie_string.strip():
        raise SubstackAuthError("No Substack cookie provided.")

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Referer": "https://substack.com/",
            "Origin": "https://substack.com",
        }
    )

    # Parse cookie string → individual cookies
    for part in cookie_string.split(";"):
        part = part.strip()
        if "=" in part:
            name, _, value = part.partition("=")
            session.cookies.set(name.strip(), value.strip(), domain=".substack.com")

    log.info("Substack session built with %d cookies", len(session.cookies))
    return session


def validate_session(session: requests.Session) -> bool:
    """Return True if the session is authenticated (hits /api/v1/user endpoint)."""
    try:
        r = session.get("https://substack.com/api/v1/user", timeout=10)
        if r.status_code == 200:
            data = r.json()
            log.info("Authenticated as: %s", data.get("email", "unknown"))
            return True
        log.warning("Auth check returned HTTP %s", r.status_code)
        return False
    except Exception as exc:
        log.error("Auth validation error: %s", exc)
        return False


def get_session_from_state(cookie: Optional[str] = None) -> requests.Session:
    """
    Convenience wrapper: build session from provided cookie or raise.
    Raises SubstackAuthError if no cookie given.
    """
    from config.settings import SUBSTACK_COOKIE
    effective = cookie or SUBSTACK_COOKIE
    if not effective:
        raise SubstackAuthError(
            "No Substack cookie found. Paste your cookie in the sidebar."
        )
    return build_session(effective)
