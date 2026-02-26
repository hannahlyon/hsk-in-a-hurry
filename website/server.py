"""FastAPI server for the HSK in a Hurry subscriber website."""
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# Ensure project root is on sys.path so database/ and config/ are importable
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import bcrypt
import jwt
import markdown as md_lib
import stripe
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr

load_dotenv(_PROJECT_ROOT / ".env")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")
JWT_SECRET = os.getenv("JWT_SECRET", "change-me")
WEBSITE_BASE_URL = os.getenv("LOCAL_DEV_URL") or os.getenv("WEBSITE_BASE_URL", "http://localhost:8001")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24

stripe.api_key = STRIPE_SECRET_KEY

_STATIC      = Path(__file__).parent / "static"
_ARCHIVE_DIR = Path(__file__).parent / "archive"

# ---------------------------------------------------------------------------
# Database helpers (imported lazily to avoid import errors at startup)
# ---------------------------------------------------------------------------
from database.db import (
    create_user,
    get_generated_post,
    get_generated_posts,
    get_user_by_email,
    get_user_by_id,
    init_db,
    update_user_subscription,
)
from website.email import send_welcome_email

init_db()


# ---------------------------------------------------------------------------
# Markdown archive helpers
# ---------------------------------------------------------------------------
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_md_file(path: Path) -> dict:
    """Parse a Markdown file with optional YAML-style frontmatter."""
    raw = path.read_text(encoding="utf-8")
    meta: dict = {}
    body = raw

    m = _FRONTMATTER_RE.match(raw)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                key, _, val = line.partition(":")
                meta[key.strip().lower()] = val.strip()
        body = raw[m.end():]

    slug = path.stem  # filename without .md
    title = meta.get("title") or slug.replace("-", " ").replace("_", " ").title()
    date_str = meta.get("date", "")
    level = meta.get("level", "")
    tags = meta.get("tags", "")

    content_html = md_lib.markdown(body, extensions=["tables", "fenced_code"])

    return {
        "id": f"file:{slug}",
        "slug": slug,
        "title": title,
        "level": level,
        "exam": "HSK",
        "content_type": tags.split(",")[0].strip() if tags else "story",
        "created_at": date_str,
        "content_html": content_html,
        "content_raw": body,
        "source": "file",
    }


def _list_md_posts() -> list:
    if not _ARCHIVE_DIR.exists():
        return []
    posts = []
    for path in sorted(_ARCHIVE_DIR.glob("*.md"), reverse=True):
        try:
            posts.append(_parse_md_file(path))
        except Exception:
            pass
    return posts


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="HSK in a Hurry")
app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

try:
    from api.main import router as _automation_router
    app.include_router(_automation_router, prefix="/automation")
except Exception as _e:
    import traceback
    print("WARNING: automation router failed to load:", _e)
    traceback.print_exc()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class CheckoutRequest(BaseModel):
    email: str


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------
def _create_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def _get_current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.split(" ", 1)[1]
    payload = _decode_token(token)
    user = get_user_by_id(int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def _require_paid(user: dict = Depends(_get_current_user)) -> dict:
    if user["subscription_status"] != "active":
        raise HTTPException(status_code=403, detail="Active subscription required")
    return user


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------
@app.get("/")
def index():
    return FileResponse(_STATIC / "index.html")


@app.get("/archive")
def archive():
    return FileResponse(_STATIC / "archive.html")


@app.get("/newsletters")
def newsletters_redirect():
    return RedirectResponse(url="/archive", status_code=301)


@app.get("/login")
def login_page():
    return FileResponse(_STATIC / "login.html")


@app.get("/success")
def success_page():
    return FileResponse(_STATIC / "success.html")


# ---------------------------------------------------------------------------
# Auth API
# ---------------------------------------------------------------------------
@app.post("/api/auth/register")
def register(req: RegisterRequest):
    existing = get_user_by_email(req.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    pw_hash = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()
    user_id = create_user(name=req.name, email=req.email, password_hash=pw_hash)
    return {"user_id": user_id}


@app.post("/api/auth/login")
def login(req: LoginRequest):
    user = get_user_by_email(req.email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not bcrypt.checkpw(req.password.encode(), user["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = _create_token(user["id"])
    return {"token": token, "subscription_status": user["subscription_status"]}


@app.get("/api/auth/me")
def me(current_user: dict = Depends(_get_current_user)):
    return {
        "id": current_user["id"],
        "name": current_user["name"],
        "email": current_user["email"],
        "subscription_status": current_user["subscription_status"],
    }


# ---------------------------------------------------------------------------
# Stripe API
# ---------------------------------------------------------------------------
@app.post("/api/stripe/checkout")
def create_checkout(req: CheckoutRequest):
    user = get_user_by_email(req.email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found — register first")
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
            customer_email=req.email,
            success_url=f"{WEBSITE_BASE_URL}/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{WEBSITE_BASE_URL}/",
            metadata={"user_id": str(user["id"]), "email": req.email},
            allow_promotion_codes=True,
        )
        return {"url": session.url}
    except stripe.StripeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        email = session.get("customer_email") or session.get("metadata", {}).get("email")
        customer_id = session.get("customer")
        subscription_id = session.get("subscription")
        if email:
            update_user_subscription(
                email=email,
                status="active",
                stripe_customer_id=customer_id,
                subscription_id=subscription_id,
            )
            user = get_user_by_email(email)
            name = user["name"] if user else email.split("@")[0]
            try:
                send_welcome_email(to_email=email, to_name=name)
            except Exception:
                pass  # don't fail the webhook if email errors
    elif event["type"] in ("customer.subscription.deleted", "customer.subscription.paused"):
        sub = event["data"]["object"]
        customer_id = sub.get("customer")
        # Look up email from user table by stripe_customer_id
        from database.db import get_connection
        with get_connection() as conn:
            row = conn.execute(
                "SELECT email FROM website_users WHERE stripe_customer_id = ?",
                (customer_id,),
            ).fetchone()
        if row:
            update_user_subscription(email=row["email"], status="cancelled")

    return {"received": True}


# ---------------------------------------------------------------------------
# Posts API
# ---------------------------------------------------------------------------
@app.get("/api/posts")
def list_posts():
    return [
        {
            "id": p["id"],
            "title": p["title"],
            "level": p["level"],
            "exam": p["exam"],
            "content_type": p["content_type"],
            "created_at": p["created_at"],
        }
        for p in _list_md_posts()
    ]


@app.get("/api/posts/{post_id:path}")
def get_post(post_id: str, current_user: dict = Depends(_require_paid)):
    # File-based post: id is "file:<slug>"
    if post_id.startswith("file:"):
        slug = post_id[5:]
        path = _ARCHIVE_DIR / f"{slug}.md"
        if not path.exists():
            raise HTTPException(status_code=404, detail="Post not found")
        return _parse_md_file(path)
    # DB post: id is a numeric string
    try:
        db_id = int(post_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Post not found")
    post = get_generated_post(db_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post
