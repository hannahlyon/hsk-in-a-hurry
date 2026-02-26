"""FastAPI webhook server — exposes the generation pipeline to Make.com."""
import re
import sys
from pathlib import Path
from typing import List, Optional

# Ensure project root is on sys.path so all project imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config.settings import DATA_DIR, SUBSTACK_COOKIE
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


# Wire router into standalone app (used when running api/main.py directly)
app.include_router(router)
