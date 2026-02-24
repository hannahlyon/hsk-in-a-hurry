"""Tab 4 — Social Media Artifact Generation."""
import base64
import re

import streamlit as st

from config.settings import ANTHROPIC_API_KEY, OPENAI_API_KEY, DALLE_MODEL, CLAUDE_MODEL, DATA_DIR
from database.db import get_newsletters, get_generated_posts
from utils.logger import get_logger

log = get_logger(__name__)

PLATFORMS = {
    "Instagram": {
        "image_size": "1024x1024",
        "caption_max": 2200,
        "hashtags": 10,
        "tone": "visual, inspirational, use emojis",
    },
    "Twitter / X": {
        "image_size": "1792x1024",
        "caption_max": 280,
        "hashtags": 3,
        "tone": "concise and punchy",
    },
    "LinkedIn": {
        "image_size": "1792x1024",
        "caption_max": 700,
        "hashtags": 5,
        "tone": "professional and educational",
    },
    "Facebook": {
        "image_size": "1792x1024",
        "caption_max": 500,
        "hashtags": 5,
        "tone": "friendly and community-focused",
    },
}


def _make_dalle_prompt(post: dict, platform: str) -> str:
    from anthropic import Anthropic
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    snippet = (post.get("content_raw") or "")[:400]
    resp = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=200,
        messages=[{"role": "user", "content": (
            f"Write a DALL-E 3 image generation prompt for a {platform} post "
            f"promoting a {post['language']} language learning lesson at "
            f"{post['level']} level. Topic: {post['title']}.\n\n"
            f"Lesson content snippet (for context):\n{snippet}\n\n"
            "Requirements:\n"
            "- Visually striking scene that evokes the language and culture\n"
            "- Do NOT include any text, letters, or written characters in the image\n"
            "- Educational, inviting atmosphere\n"
            "- Return only the prompt, nothing else"
        )}],
    )
    return resp.content[0].text.strip()


def _generate_caption(post: dict, platform: str, specs: dict) -> str:
    from anthropic import Anthropic
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    snippet = (post.get("content_raw") or "")[:1500]
    resp = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=600,
        messages=[{"role": "user", "content": (
            f"Write a {platform} caption for a language learning post.\n\n"
            f"Lesson details:\n"
            f"- Language: {post['language']}, Level: {post['level']}\n"
            f"- Title: {post['title']}\n"
            f"- Content snippet:\n{snippet}\n\n"
            f"Requirements:\n"
            f"- Tone: {specs['tone']}\n"
            f"- Maximum {specs['caption_max']} characters total (including hashtags)\n"
            f"- Include exactly {specs['hashtags']} hashtags\n"
            f"- Hook the audience — don't reproduce the full lesson\n"
            f"- Return only the caption text with hashtags, nothing else"
        )}],
    )
    return resp.content[0].text.strip()


def _generate_image(dalle_prompt: str, image_size: str) -> bytes:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    resp = client.images.generate(
        model=DALLE_MODEL,
        prompt=dalle_prompt,
        size=image_size,
        quality="standard",
        n=1,
        response_format="b64_json",
    )
    return base64.b64decode(resp.data[0].b64_json)


def render():
    st.header("Social Media")
    st.markdown(
        "Pick a lesson from your database and generate a platform-ready image and caption."
    )

    if not ANTHROPIC_API_KEY or not OPENAI_API_KEY:
        st.error("Both ANTHROPIC_API_KEY and OPENAI_API_KEY must be set in `.env`.")
        return

    # ── Selectors ──────────────────────────────────────────────────────────
    newsletters = get_newsletters()
    if not newsletters:
        st.warning("No newsletters yet. Create one in Tab 1 first.")
        return

    nl_map = {f"{n['name']} ({n['language']} / {n['exam']})": n for n in newsletters}
    nl = nl_map[st.selectbox("Newsletter", list(nl_map.keys()), key="social_nl")]

    posts = get_generated_posts(nl["id"])
    if not posts:
        st.info("No generated posts for this newsletter yet. Use Tab 2 to generate some.")
        return

    post_map = {
        f"[{p['level']}] {p['title']}  ({p['created_at'][:10]})": p
        for p in posts
    }
    post = post_map[st.selectbox("Lesson", list(post_map.keys()), key="social_post")]

    col_plat, col_info = st.columns([1, 2])
    with col_plat:
        platform = st.selectbox("Platform", list(PLATFORMS.keys()), key="social_platform")
    specs = PLATFORMS[platform]
    with col_info:
        st.markdown(
            f"**Image:** {specs['image_size']} &nbsp;|&nbsp; "
            f"**Caption:** ≤ {specs['caption_max']} chars &nbsp;|&nbsp; "
            f"**Hashtags:** {specs['hashtags']} &nbsp;|&nbsp; "
            f"**Tone:** {specs['tone']}"
        )

    st.divider()

    # ── Generate ───────────────────────────────────────────────────────────
    if st.button("Generate", type="primary", key="social_generate"):
        dalle_prompt = caption = ""
        img_bytes = None

        with st.spinner("Crafting image prompt…"):
            try:
                dalle_prompt = _make_dalle_prompt(post, platform)
            except Exception as exc:
                st.error(f"Image prompt failed: {exc}")
                return

        with st.spinner("Writing caption…"):
            try:
                caption = _generate_caption(post, platform, specs)
            except Exception as exc:
                st.error(f"Caption generation failed: {exc}")
                return

        with st.spinner("Generating image with DALL-E 3…"):
            try:
                img_bytes = _generate_image(dalle_prompt, specs["image_size"])
            except Exception as exc:
                st.error(f"Image generation failed: {exc}")
                return

        # Persist to session state so it survives widget interactions
        st.session_state["social_result"] = {
            "caption": caption,
            "img_bytes": img_bytes,
            "dalle_prompt": dalle_prompt,
            "post_id": post["id"],
            "platform": platform,
            "platform_slug": re.sub(r"[^a-z0-9]+", "_", platform.lower()).strip("_"),
        }

        # Save image to disk
        platform_slug = st.session_state["social_result"]["platform_slug"]
        img_dir = DATA_DIR / "social_images" / str(post["id"])
        img_dir.mkdir(parents=True, exist_ok=True)
        (img_dir / f"{platform_slug}.png").write_bytes(img_bytes)
        log.info("Saved social image: %s", img_dir / f"{platform_slug}.png")

    # ── Display result (persists after generation) ─────────────────────────
    result = st.session_state.get("social_result")
    if result:
        col_img, col_text = st.columns(2)

        with col_img:
            st.subheader("Image")
            st.image(result["img_bytes"], use_container_width=True)
            st.download_button(
                "⬇ Download Image",
                data=result["img_bytes"],
                file_name=f"{result['platform_slug']}_{result['post_id']}.png",
                mime="image/png",
            )
            with st.expander("DALL-E prompt used"):
                st.text(result["dalle_prompt"])

        with col_text:
            st.subheader("Caption")
            edited = st.text_area(
                "Edit before posting",
                value=result["caption"],
                height=300,
                key="social_caption_edit",
            )
            char_count = len(edited)
            limit = PLATFORMS[result["platform"]]["caption_max"]
            colour = "green" if char_count <= limit else "red"
            st.markdown(f":{colour}[{char_count} / {limit} characters]")
            st.download_button(
                "⬇ Download Caption",
                data=edited,
                file_name=f"{result['platform_slug']}_{result['post_id']}_caption.txt",
                mime="text/plain",
            )
