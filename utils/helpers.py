"""Utility helpers: slugify, date formatting, sanitize."""
import re
import unicodedata
from datetime import datetime
from typing import Optional


def slugify(text: str) -> str:
    """Convert text to URL-safe slug."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return text


def sanitize_html(text: str) -> str:
    """Basic HTML entity escaping."""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
    )


def fmt_date(dt: Optional[datetime] = None, fmt: str = "%Y-%m-%d") -> str:
    if dt is None:
        dt = datetime.utcnow()
    return dt.strftime(fmt)


def truncate(text: str, max_len: int = 200, suffix: str = "...") -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - len(suffix)] + suffix


def chunk_list(lst: list, size: int) -> list:
    """Split list into chunks of given size."""
    return [lst[i : i + size] for i in range(0, len(lst), size)]
