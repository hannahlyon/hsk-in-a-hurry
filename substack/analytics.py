"""Fetch analytics from Substack internal API endpoints."""
import json
from datetime import date
from typing import Optional
import requests

from substack.auth import SubstackAuthError
from utils.logger import get_logger

log = get_logger(__name__)

# Endpoint URL templates (subdomain-prefixed)
_SUMMARY_URL = "https://{sub}.substack.com/api/v1/publish-dashboard/summary-v2?range={days}"
_EMAIL_STATS_URL = "https://{sub}.substack.com/api/v1/publication/stats/email_stats"
_POSTS_URL = "https://{sub}.substack.com/api/v1/publication/stats/posts?range={days}"


def fetch_summary(session: requests.Session, subdomain: str,
                  days: int = 30) -> Optional[dict]:
    """Fetch subscriber/view summary. Returns parsed dict or None."""
    url = _SUMMARY_URL.format(sub=subdomain, days=days)
    try:
        r = session.get(url, timeout=15)
        if r.status_code in (401, 403):
            raise SubstackAuthError(f"Auth failed fetching summary: HTTP {r.status_code}")
        if r.status_code == 200:
            return r.json()
        log.warning("Summary fetch HTTP %s", r.status_code)
        return None
    except SubstackAuthError:
        raise
    except Exception as exc:
        log.error("fetch_summary error: %s", exc)
        return None


def fetch_email_stats(session: requests.Session,
                      subdomain: str) -> Optional[dict]:
    """Fetch per-post email open/click stats."""
    url = _EMAIL_STATS_URL.format(sub=subdomain)
    try:
        r = session.get(url, timeout=15)
        if r.status_code in (401, 403):
            raise SubstackAuthError(f"Auth failed fetching email stats: HTTP {r.status_code}")
        if r.status_code == 200:
            return r.json()
        log.warning("Email stats fetch HTTP %s", r.status_code)
        return None
    except SubstackAuthError:
        raise
    except Exception as exc:
        log.error("fetch_email_stats error: %s", exc)
        return None


def fetch_post_stats(session: requests.Session, subdomain: str,
                     days: int = 30) -> Optional[list]:
    """Fetch per-post view stats list."""
    url = _POSTS_URL.format(sub=subdomain, days=days)
    try:
        r = session.get(url, timeout=15)
        if r.status_code in (401, 403):
            raise SubstackAuthError(f"Auth failed fetching post stats: HTTP {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            # May be a list or {"posts": [...]}
            if isinstance(data, list):
                return data
            return data.get("posts", [])
        log.warning("Post stats fetch HTTP %s", r.status_code)
        return None
    except SubstackAuthError:
        raise
    except Exception as exc:
        log.error("fetch_post_stats error: %s", exc)
        return None


def parse_summary_to_db_format(raw: dict, days: int) -> dict:
    """Normalise raw summary JSON to DB insert dict."""
    subs = raw.get("subscriberCount") or raw.get("total_subscribers", {})
    if isinstance(subs, dict):
        total = subs.get("total", 0)
        paid = subs.get("paid", 0)
        free = subs.get("free", total - paid)
    else:
        total = subs or 0
        paid = raw.get("paid_subscribers", 0)
        free = total - paid

    return {
        "total_subscribers": total,
        "paid_subscribers": paid,
        "free_subscribers": free,
        "total_views": raw.get("totalViews") or raw.get("total_views", 0),
        "open_rate_30d": raw.get("openRate") or raw.get("open_rate_30d"),
        "new_subs_period": raw.get("newSubscribers") or raw.get("new_subs_period", 0),
        "snapshot_raw": json.dumps(raw),
    }


def parse_post_stats_to_db(post: dict) -> dict:
    """Normalise a single post stats dict to DB format."""
    return {
        "post_id": str(post.get("id", "")),
        "post_title": post.get("title", ""),
        "published_at": post.get("published_at") or post.get("publishedAt"),
        "emails_sent": post.get("emailsSent") or post.get("emails_sent", 0),
        "emails_opened": post.get("emailsOpened") or post.get("emails_opened", 0),
        "open_rate": post.get("openRate") or post.get("open_rate"),
        "total_views": post.get("totalViews") or post.get("total_views", 0),
        "unique_views": post.get("uniqueViews") or post.get("unique_views", 0),
        "clicks": post.get("totalClicks") or post.get("clicks", 0),
    }
