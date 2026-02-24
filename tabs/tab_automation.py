"""Tab 5 — Automation: batch content generation + social asset generation with job log."""
import re
from pathlib import Path

import streamlit as st

from config.settings import ANTHROPIC_API_KEY, OPENAI_API_KEY, DATA_DIR
from database.db import (
    get_newsletters,
    get_generated_posts,
    get_social_posts,
    insert_generated_post,
    insert_social_post,
)
from rag.retriever import retrieve_for_generation
from rag.generator import generate_content, generate_title
from tabs.tab_social import PLATFORMS, _make_dalle_prompt, _generate_caption, _generate_image
from utils.logger import get_logger

log = get_logger(__name__)

CONTENT_FORMATS = ["story", "blurb", "dialogue", "matching"]


def _run_content_generation(newsletter: dict, levels: list, theme: str, content_format: str):
    """Generate content for each selected level and save to DB. Returns list of result dicts."""
    language = newsletter["language"]
    exam = newsletter["exam"]
    results = []

    for level in levels:
        with st.status(f"Generating content for **{level}**…", expanded=False) as status:
            try:
                st.write("Retrieving context from vector store…")
                grammar_chunks, vocab_chunks = retrieve_for_generation(
                    language, exam, level, theme
                )
                st.write(
                    f"Retrieved {len(grammar_chunks)} grammar + {len(vocab_chunks)} vocab chunks."
                )

                st.write("Generating content with Claude…")
                content_raw = generate_content(
                    language, exam, level, theme, content_format,
                    grammar_chunks, vocab_chunks,
                )

                st.write("Generating title…")
                title = generate_title(content_raw, language, level)

                post_id = insert_generated_post(
                    newsletter_id=newsletter["id"],
                    title=title,
                    content_type=content_format,
                    language=language,
                    exam=exam,
                    level=level,
                    content_raw=content_raw,
                )

                status.update(
                    label=f"✅ **{level}** — id={post_id} · \"{title}\"",
                    state="complete",
                )
                results.append({"level": level, "post_id": post_id, "title": title, "ok": True})
                log.info("Automation: saved post id=%d %s %s", post_id, level, title)

            except Exception as exc:
                status.update(label=f"❌ **{level}** — {exc}", state="error")
                log.error("Automation content error (%s): %s", level, exc)
                results.append({"level": level, "error": str(exc), "ok": False})

    return results


def _run_social_generation(post: dict, platforms: list):
    """Generate social assets for each selected platform. Returns list of result dicts."""
    results = []

    for platform in platforms:
        specs = PLATFORMS[platform]
        platform_slug = re.sub(r"[^a-z0-9]+", "_", platform.lower()).strip("_")

        with st.status(f"Generating assets for **{platform}**…", expanded=False) as status:
            try:
                st.write("Crafting DALL-E image prompt…")
                dalle_prompt = _make_dalle_prompt(post, platform)

                st.write("Writing caption…")
                caption = _generate_caption(post, platform, specs)

                st.write("Generating image with DALL-E 3…")
                img_bytes = _generate_image(dalle_prompt, specs["image_size"])

                img_dir = DATA_DIR / "social_images" / str(post["id"])
                img_dir.mkdir(parents=True, exist_ok=True)
                img_path = img_dir / f"{platform_slug}.png"
                img_path.write_bytes(img_bytes)

                social_id = insert_social_post(
                    generated_post_id=post["id"],
                    platform=platform,
                    copy_text=caption,
                    image_prompt=dalle_prompt,
                    image_path=str(img_path),
                    image_size=specs["image_size"],
                )

                status.update(
                    label=f"✅ **{platform}** — {img_path.name}  (id={social_id})",
                    state="complete",
                )
                results.append({
                    "platform": platform, "social_id": social_id,
                    "img_path": str(img_path), "ok": True,
                })
                log.info("Automation: saved social_post id=%d %s", social_id, platform)

            except Exception as exc:
                status.update(label=f"❌ **{platform}** — {exc}", state="error")
                log.error("Automation social error (%s): %s", platform, exc)
                results.append({"platform": platform, "error": str(exc), "ok": False})

    return results


def render():
    st.header("Automation")
    st.markdown(
        "Run the full content → social pipeline in batch, "
        "or trigger individual stages from the UI."
    )

    if not ANTHROPIC_API_KEY or not OPENAI_API_KEY:
        st.error("Both **ANTHROPIC_API_KEY** and **OPENAI_API_KEY** must be set in `.env`.")
        return

    newsletters = get_newsletters()

    # ── Section 1: Batch Content Generation ────────────────────────────────
    st.subheader("1 · Generate Batch Content")

    if not newsletters:
        st.warning("No newsletters found. Create one in Tab 1 first.")
    else:
        nl_map = {f"{n['name']} ({n['language']} / {n['exam']})": n for n in newsletters}
        nl = nl_map[st.selectbox("Newsletter", list(nl_map.keys()), key="auto_nl")]

        # Derive available levels from existing posts (or let user type freely)
        existing_posts = get_generated_posts(nl["id"])
        known_levels = sorted({p["level"] for p in existing_posts if p.get("level")})

        col_a, col_b, col_c = st.columns([2, 2, 2])
        with col_a:
            levels_input = st.text_input(
                "Levels (comma-separated)",
                placeholder="e.g. HSK3, HSK4",
                key="auto_levels",
                help="Enter level codes separated by commas.",
            )
        with col_b:
            theme = st.text_input("Theme / topic", placeholder="e.g. ordering food", key="auto_theme")
        with col_c:
            content_format = st.selectbox("Format", CONTENT_FORMATS, key="auto_format")

        if st.button("▶ Generate Content", type="primary", key="auto_gen_content"):
            levels = [lv.strip() for lv in levels_input.split(",") if lv.strip()]
            if not levels:
                st.warning("Enter at least one level.")
            elif not theme.strip():
                st.warning("Enter a theme.")
            else:
                results = _run_content_generation(nl, levels, theme.strip(), content_format)
                ok_count = sum(1 for r in results if r["ok"])
                st.success(f"Generated {ok_count}/{len(results)} posts successfully.")

    st.divider()

    # ── Section 2: Social Asset Generation ─────────────────────────────────
    st.subheader("2 · Generate Social Assets")

    all_posts = get_generated_posts()
    if not all_posts:
        st.info("No generated posts yet. Use Section 1 or Tab 2 to create some.")
    else:
        post_map = {
            f"[id={p['id']}] [{p['level']}] {p['title']}  ({(p['created_at'] or '')[:10]})": p
            for p in all_posts
        }
        selected_post = post_map[
            st.selectbox("Post", list(post_map.keys()), key="auto_social_post")
        ]

        selected_platforms = st.multiselect(
            "Platforms",
            list(PLATFORMS.keys()),
            default=list(PLATFORMS.keys()),
            key="auto_platforms",
        )

        if st.button("▶ Generate Social Assets", type="primary", key="auto_gen_social"):
            if not selected_platforms:
                st.warning("Select at least one platform.")
            else:
                results = _run_social_generation(selected_post, selected_platforms)
                ok_count = sum(1 for r in results if r["ok"])
                st.success(f"Generated assets for {ok_count}/{len(results)} platforms.")

    st.divider()

    # ── Section 3: Job Log ──────────────────────────────────────────────────
    st.subheader("3 · Job Log")

    with st.expander("Content Posts", expanded=True):
        posts = get_generated_posts()
        if posts:
            import pandas as pd
            df = pd.DataFrame(posts)[
                ["id", "language", "exam", "level", "content_type", "title", "created_at"]
            ].rename(columns={"content_type": "format"})
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No posts yet.")

    with st.expander("Social Assets", expanded=False):
        if not all_posts:
            st.info("No posts yet.")
        else:
            import pandas as pd
            rows = []
            for p in all_posts:
                for sp in get_social_posts(p["id"]):
                    rows.append(sp)
            if rows:
                df_social = pd.DataFrame(rows)[
                    ["id", "generated_post_id", "platform", "image_path", "created_at"]
                ].rename(columns={"generated_post_id": "post_id"})
                st.dataframe(df_social, use_container_width=True, hide_index=True)
            else:
                st.info("No social assets yet.")
