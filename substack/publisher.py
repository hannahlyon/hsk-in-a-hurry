"""Create and publish drafts via Substack's internal API."""
import json
from typing import Optional
from urllib.parse import urlparse

import requests

from substack.auth import SubstackAuthError, build_session
from utils.logger import get_logger

log = get_logger(__name__)

_DRAFTS_URL = "https://{sub}.substack.com/api/v1/drafts"
_PUBLISH_URL = "https://{sub}.substack.com/api/v1/drafts/{id}/publish"


def _text_to_prosemirror(text: str) -> str:
    """
    Convert plain text to a stringified ProseMirror document.
    Splits on double newlines for paragraphs, single newlines become hard breaks.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    content = []
    for para in paragraphs:
        lines = para.split("\n")
        inline = []
        for i, line in enumerate(lines):
            if line:
                inline.append({"type": "text", "text": line})
            if i < len(lines) - 1:
                inline.append({"type": "hardBreak"})
        content.append({"type": "paragraph", "content": inline} if inline
                        else {"type": "paragraph"})

    doc = {
        "type": "doc",
        "attrs": {"schemaVersion": "v1"},
        "content": content or [{"type": "paragraph"}],
    }
    return json.dumps(doc)


def _resolve_subdomain(subdomain: str, session: requests.Session) -> str:
    """
    Follow any redirect on the root page to get Substack's canonical subdomain.
    e.g. 'hsk-hurry' → 'hskhurry' (Substack strips hyphens internally).
    """
    try:
        r = session.get(
            f"https://{subdomain}.substack.com/",
            allow_redirects=True,
            timeout=10,
        )
        host = urlparse(r.url).hostname or ""
        parts = host.split(".")
        if len(parts) >= 3 and parts[-2] == "substack":
            resolved = parts[0]
            if resolved != subdomain:
                log.info("Subdomain resolved: %s -> %s", subdomain, resolved)
            return resolved
    except Exception as exc:
        log.warning("Could not resolve subdomain %s: %s", subdomain, exc)
    return subdomain


def _get_author_id(subdomain: str, session: requests.Session) -> Optional[int]:
    """
    Fetch the publication's author ID from existing drafts (publishedBylines).
    Required by Substack's draft_bylines field since mid-2025.
    """
    try:
        r = session.get(
            f"https://{subdomain}.substack.com/api/v1/drafts",
            timeout=10,
        )
        if r.ok:
            for draft in r.json():
                for byline in draft.get("publishedBylines") or []:
                    if byline.get("id"):
                        return byline["id"]
    except Exception as exc:
        log.warning("Could not fetch author id for %s: %s", subdomain, exc)
    return None


def create_draft(subdomain: str, cookie_string: str,
                  title: str, body_text: str) -> dict:
    """
    Create a Substack draft. Returns the full draft dict including its id.
    Raises SubstackAuthError on 401/403, requests.HTTPError on other failures.
    """
    session = build_session(cookie_string)

    # Resolve canonical subdomain (Substack may redirect hsk-hurry → hskhurry)
    real_sub = _resolve_subdomain(subdomain, session)
    author_id = _get_author_id(real_sub, session)

    url = _DRAFTS_URL.format(sub=real_sub)
    pub_origin = f"https://{real_sub}.substack.com"
    session.headers.update({"Referer": pub_origin + "/", "Origin": pub_origin})

    payload = {
        "draft_title": title,
        "draft_subtitle": "",
        "draft_body": _text_to_prosemirror(body_text),
        "draft_bylines": [{"id": author_id}] if author_id else [],
        "audience": "everyone",
        "type": "newsletter",
        "section_chosen": False,
        "draft_podcast_url": "",
        "draft_podcast_duration": None,
        "draft_video_upload_id": None,
        "draft_podcast_upload_id": None,
        "draft_podcast_preview_upload_id": None,
        "draft_voiceover_upload_id": None,
        "explicit": False,
    }

    log.info("Creating Substack draft: '%s' on %s.substack.com", title, real_sub)
    r = session.post(url, json=payload, timeout=30)

    if r.status_code in (401, 403):
        raise SubstackAuthError(f"Auth failed creating draft: HTTP {r.status_code}")
    r.raise_for_status()

    draft = r.json()
    if not isinstance(draft, dict):
        raise SubstackAuthError(
            f"Unexpected response from drafts endpoint (got {type(draft).__name__}). "
            "Cookie may be invalid or subdomain resolution failed."
        )
    log.info("Draft created: id=%s url=%s", draft.get("id"), draft.get("canonical_url"))
    return draft


def publish_draft(subdomain: str, cookie_string: str,
                   draft_id: int, send_email: bool = True) -> dict:
    """
    Publish an existing draft. Returns the published post dict.
    send_email=True sends to all subscribers immediately.
    """
    session = build_session(cookie_string)

    real_sub = _resolve_subdomain(subdomain, session)
    url = _PUBLISH_URL.format(sub=real_sub, id=draft_id)
    pub_origin = f"https://{real_sub}.substack.com"
    session.headers.update({"Referer": pub_origin + "/", "Origin": pub_origin})

    payload = {
        "audience": "everyone",
        "send_email": send_email,
    }

    log.info("Publishing Substack draft id=%s (send_email=%s)", draft_id, send_email)
    r = session.post(url, json=payload, timeout=30)

    if r.status_code in (401, 403):
        raise SubstackAuthError(f"Auth failed publishing draft: HTTP {r.status_code}")
    r.raise_for_status()

    post = r.json()
    log.info("Published: %s", post.get("canonical_url"))
    return post
