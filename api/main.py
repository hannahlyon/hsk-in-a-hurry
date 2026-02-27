"""FastAPI webhook server — exposes the generation pipeline to Make.com."""
import random
import re
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import List, Optional

# Ensure project root is on sys.path so all project imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

import markdown as md
import stripe
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config.languages import EXAM_CONFIGS
from config.settings import (
    DATA_DIR, SUBSTACK_COOKIE,
    TWITTER_API_KEY, TWITTER_API_SECRET,
    TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET,
    STRIPE_SECRET_KEY, EMAIL_FROM, EMAIL_APP_PASSWORD,
)
from database.db import (
    init_db,
    get_newsletter,
    get_newsletters,
    get_generated_post,
    insert_generated_post,
    insert_social_post,
)
from rag.generator import generate_content, generate_title
from rag.retriever import retrieve_for_generation, get_retrieval_ids
from substack.auth import SubstackAuthError
from substack.publisher import create_draft, publish_draft
from tabs.tab_social import PLATFORMS, _generate_caption, _generate_image, _make_dalle_prompt

router = APIRouter()

app = FastAPI(title="Newsletter Automation API")


@app.on_event("startup")
def startup() -> None:
    init_db()


# ── Request / Response models ────────────────────────────────────────────────

class GenerateContentRequest(BaseModel):
    newsletter_id: int
    level: str
    theme: Optional[str] = None    # omit to let Claude pick a topic automatically
    content_format: str = "story"


class GenerateContentResponse(BaseModel):
    post_id: int
    title: str
    language: str
    exam: str
    level: str
    content_preview: str
    content_raw: str
    grammar_chunks_used: int
    vocab_chunks_used: int


class GenerateSocialRequest(BaseModel):
    post_id: int
    platforms: List[str]


class SocialAsset(BaseModel):
    platform: str
    social_post_id: int
    caption: str
    image_url: str


class GenerateSocialResponse(BaseModel):
    post_id: int
    assets: List[SocialAsset]


class RandomParamsResponse(BaseModel):
    newsletter_id: int
    level: str
    theme: str
    content_format: str


_CONTENT_FORMATS = ["blurb", "story", "dialogue", "matching"]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _auto_theme(language: str, exam: str, level: str) -> str:
    """Ask Claude to suggest a practical, everyday lesson topic for this language/level."""
    import anthropic
    from config.settings import ANTHROPIC_API_KEY, CLAUDE_MODEL
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=50,
        messages=[{"role": "user", "content": (
            f"Suggest one practical, everyday lesson topic for a {language} {exam} {level} "
            f"language learning newsletter. Return only the topic phrase, nothing else. "
            f"Examples: 'ordering coffee', 'asking for directions', 'shopping at a market'."
        )}],
    )
    return resp.content[0].text.strip()


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/newsletters")
def list_newsletters():
    """Return all newsletters. Make uses this to resolve newsletter_id."""
    return get_newsletters()


@router.get("/random-params", response_model=RandomParamsResponse)
def random_params_endpoint(newsletter_id: int):
    """Return randomly selected level + content_format + Claude-generated theme for a newsletter."""
    newsletter = get_newsletter(newsletter_id)
    if not newsletter:
        raise HTTPException(status_code=404, detail=f"Newsletter {newsletter_id} not found")

    language = newsletter["language"]
    exam = newsletter["exam"]

    config = next(
        (c for c in EXAM_CONFIGS.values() if c.language == language and c.exam == exam),
        None,
    )
    if not config:
        raise HTTPException(status_code=400, detail=f"No exam config found for {language} {exam}")

    level = random.choice(config.levels)
    content_format = random.choice(_CONTENT_FORMATS)
    theme = _auto_theme(language, exam, level)

    return RandomParamsResponse(
        newsletter_id=newsletter_id,
        level=level,
        theme=theme,
        content_format=content_format,
    )


@router.post("/generate-content", response_model=GenerateContentResponse)
def generate_content_endpoint(req: GenerateContentRequest):
    """Run retrieve → generate → title → save; returns post_id + full content."""
    newsletter = get_newsletter(req.newsletter_id)
    if not newsletter:
        raise HTTPException(status_code=404, detail=f"Newsletter {req.newsletter_id} not found")

    language = newsletter["language"]
    exam = newsletter["exam"]
    theme = req.theme or _auto_theme(language, exam, req.level)

    grammar_chunks, vocab_chunks = retrieve_for_generation(language, exam, req.level, theme)
    retrieval_ids = get_retrieval_ids(language, exam, req.level, theme)

    content_raw = generate_content(
        language, exam, req.level, theme, req.content_format,
        grammar_chunks, vocab_chunks,
    )

    title = generate_title(content_raw, language, req.level)

    post_id = insert_generated_post(
        newsletter_id=req.newsletter_id,
        title=title,
        content_type=req.content_format,
        language=language,
        exam=exam,
        level=req.level,
        content_raw=content_raw,
        retrieval_ids=",".join(retrieval_ids) if retrieval_ids else None,
    )

    return GenerateContentResponse(
        post_id=post_id,
        title=title,
        language=language,
        exam=exam,
        level=req.level,
        content_preview=content_raw[:500],
        content_raw=content_raw,
        grammar_chunks_used=len(grammar_chunks),
        vocab_chunks_used=len(vocab_chunks),
    )


@router.post("/generate-social", response_model=GenerateSocialResponse)
def generate_social_endpoint(req: GenerateSocialRequest, request: Request):
    """Generate DALL-E image + caption for each platform; returns assets with image URLs."""
    post = get_generated_post(req.post_id)
    if not post:
        raise HTTPException(status_code=404, detail=f"Post {req.post_id} not found")

    unknown = [p for p in req.platforms if p not in PLATFORMS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown platforms: {unknown}")

    assets: List[SocialAsset] = []

    for platform in req.platforms:
        specs = PLATFORMS[platform]
        platform_slug = re.sub(r"[^a-z0-9]+", "_", platform.lower()).strip("_")

        dalle_prompt = _make_dalle_prompt(post, platform)
        caption = _generate_caption(post, platform, specs)
        img_bytes = _generate_image(dalle_prompt, specs["image_size"])

        img_dir = DATA_DIR / "social_images" / str(post["id"])
        img_dir.mkdir(parents=True, exist_ok=True)
        img_path = img_dir / f"{platform_slug}.png"
        img_path.write_bytes(img_bytes)

        social_post_id = insert_social_post(
            generated_post_id=post["id"],
            platform=platform,
            copy_text=caption,
            image_prompt=dalle_prompt,
            image_path=str(img_path),
            image_size=specs["image_size"],
        )

        image_url = str(request.url_for("serve_image", post_id=post["id"], platform_slug=f"{platform_slug}.png"))
        assets.append(SocialAsset(
            platform=platform,
            social_post_id=social_post_id,
            caption=caption,
            image_url=image_url,
        ))

    return GenerateSocialResponse(post_id=req.post_id, assets=assets)


class PublishSubstackRequest(BaseModel):
    post_id: int
    publish: bool = False          # False = save as draft, True = publish + email subscribers
    send_email: bool = True        # only used when publish=True
    cookie: Optional[str] = None   # falls back to SUBSTACK_COOKIE in .env


class PublishSubstackResponse(BaseModel):
    post_id: int
    draft_id: int
    substack_url: str
    published: bool


@router.post("/publish-substack", response_model=PublishSubstackResponse)
def publish_substack_endpoint(req: PublishSubstackRequest):
    """Create a Substack draft (and optionally publish it) from a generated post."""
    post = get_generated_post(req.post_id)
    if not post:
        raise HTTPException(status_code=404, detail=f"Post {req.post_id} not found")

    newsletter = get_newsletter(post["newsletter_id"])
    if not newsletter or not newsletter.get("substack_url"):
        raise HTTPException(status_code=400, detail="Newsletter has no substack_url configured")

    # Derive subdomain from substack_url (e.g. "hsk-hurry.substack.com" → "hsk-hurry")
    subdomain = newsletter["substack_url"].replace("https://", "").split(".")[0]

    cookie = req.cookie or SUBSTACK_COOKIE
    if not cookie:
        raise HTTPException(status_code=400, detail="No Substack cookie provided")

    try:
        draft = create_draft(
            subdomain=subdomain,
            cookie_string=cookie,
            title=post["title"],
            body_text=post["content_raw"] or "",
        )
    except SubstackAuthError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Substack draft creation failed: {e}")

    draft_id = draft["id"]
    draft_url = draft.get("canonical_url", "")
    published = False

    if req.publish:
        try:
            result = publish_draft(
                subdomain=subdomain,
                cookie_string=cookie,
                draft_id=draft_id,
                send_email=req.send_email,
            )
            draft_url = result.get("canonical_url", draft_url)
            published = True
        except SubstackAuthError as e:
            raise HTTPException(status_code=401, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Substack publish failed: {e}")

    return PublishSubstackResponse(
        post_id=req.post_id,
        draft_id=draft_id,
        substack_url=draft_url,
        published=published,
    )


@router.get("/images/{post_id}/{platform_slug}")
def serve_image(post_id: int, platform_slug: str):
    """Serve a saved PNG as binary so Make can pass it to platform upload modules."""
    img_path = DATA_DIR / "social_images" / str(post_id) / platform_slug
    if not img_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(str(img_path), media_type="image/png")


class PostTweetRequest(BaseModel):
    text: str                              # tweet body — max 280 chars
    social_post_id: Optional[int] = None  # optional: links tweet back to a social_post row


class PostTweetResponse(BaseModel):
    tweet_id: str
    tweet_url: str
    text: str
    social_post_id: Optional[int] = None


@router.post("/post-tweet", response_model=PostTweetResponse)
def post_tweet_endpoint(req: PostTweetRequest):
    """Post a tweet via Twitter API v2.

    Make.com: add an HTTP module → POST /post-tweet with JSON body.
    Required credentials: TWITTER_API_KEY, TWITTER_API_SECRET,
    TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET in .env.
    """
    if not all([TWITTER_API_KEY, TWITTER_API_SECRET,
                TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET]):
        raise HTTPException(
            status_code=503,
            detail="Twitter credentials not configured. Set TWITTER_API_KEY, "
                   "TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET in .env.",
        )

    if len(req.text) > 280:
        raise HTTPException(status_code=422, detail=f"Tweet is {len(req.text)} chars — max 280.")

    try:
        import tweepy
        client = tweepy.Client(
            consumer_key=TWITTER_API_KEY,
            consumer_secret=TWITTER_API_SECRET,
            access_token=TWITTER_ACCESS_TOKEN,
            access_token_secret=TWITTER_ACCESS_TOKEN_SECRET,
        )
        response = client.create_tweet(text=req.text)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Twitter API error: {exc}")

    tweet_id = str(response.data["id"])
    return PostTweetResponse(
        tweet_id=tweet_id,
        tweet_url=f"https://x.com/i/web/status/{tweet_id}",
        text=req.text,
        social_post_id=req.social_post_id,
    )


class SendLessonRequest(BaseModel):
    post_id: int
    subject: Optional[str] = None        # defaults to post title
    test_emails: Optional[List[str]] = None  # if set, skips Stripe and sends only to these


class SendLessonResponse(BaseModel):
    post_id: int
    title: str
    recipients_count: int
    email_from: str


@router.post("/send-lesson", response_model=SendLessonResponse)
def send_lesson_endpoint(req: SendLessonRequest):
    """Fetch every active Stripe subscriber's email and BCC them the lesson."""
    post = get_generated_post(req.post_id)
    if not post:
        raise HTTPException(status_code=404, detail=f"Post {req.post_id} not found")
    if not EMAIL_FROM or not EMAIL_APP_PASSWORD:
        raise HTTPException(status_code=503, detail="EMAIL_FROM / EMAIL_APP_PASSWORD not configured")

    # Collect recipient emails — use test override if provided, otherwise query Stripe
    if req.test_emails:
        emails = list(dict.fromkeys(req.test_emails))
    else:
        if not STRIPE_SECRET_KEY:
            raise HTTPException(status_code=503, detail="STRIPE_SECRET_KEY not configured")
        stripe.api_key = STRIPE_SECRET_KEY
        emails = []
        for sub in stripe.Subscription.list(status="active", expand=["data.customer"]).auto_paging_iter():
            customer = sub.customer
            email = customer.get("email") if isinstance(customer, dict) else getattr(customer, "email", None)
            if email:
                emails.append(email)
        emails = list(dict.fromkeys(emails))

    if not emails:
        raise HTTPException(status_code=404, detail="No recipients found")

    # Build multipart email
    subject = req.subject or post["title"]
    body_html = md.markdown(post["content_raw"] or "")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_FROM           # sender is the visible To recipient
    msg["Bcc"] = ", ".join(emails)   # all subscribers hidden via BCC
    msg.attach(MIMEText(post["content_raw"] or "", "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    # Send via Gmail SMTP
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.login(EMAIL_FROM, EMAIL_APP_PASSWORD)
            server.sendmail(EMAIL_FROM, [EMAIL_FROM] + emails, msg.as_string())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Email send failed: {exc}")

    return SendLessonResponse(
        post_id=req.post_id,
        title=post["title"],
        recipients_count=len(emails),
        email_from=EMAIL_FROM,
    )


# Wire router into standalone app (used when running api/main.py directly)
app.include_router(router)
