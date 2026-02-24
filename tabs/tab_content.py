"""Tab 2 — Content Generation (Scrape & Index + Generate & Publish)."""
import json

import streamlit as st

from config.languages import EXAM_CONFIGS, LANGUAGE_OPTIONS, get_levels_for_exam
from database.db import (
    get_newsletters, insert_scrape_session, update_scrape_session,
    insert_chunks, mark_chunks_embedded, insert_generated_post,
    get_generated_posts,
)
from rag.generator import stream_content, generate_title
from rag.retriever import retrieve_for_generation, get_retrieval_ids
from vector_store.chroma_client import get_language_collection, collection_count
from vector_store.embedder import embed_and_upsert, make_chunk_id
from utils.logger import get_logger

log = get_logger(__name__)

CONTENT_FORMATS = ["blurb", "story", "dialogue", "matching"]
CONTENT_TYPES = ["grammar", "vocabulary", "both"]


def _get_scraper(exam_key: str):
    """Return appropriate scraper instance for the exam key."""
    if exam_key == "japanese_jlpt":
        from scraper.japanese_jlpt import JLPTScraper
        return JLPTScraper()
    elif exam_key == "spanish_dele":
        from scraper.spanish_dele import SpanishDELEScraper
        return SpanishDELEScraper()
    elif exam_key == "french_delf":
        from scraper.french_delf import FrenchDELFScraper
        return FrenchDELFScraper()
    elif exam_key == "mandarin_hsk":
        from scraper.mandarin_hsk import MandarinHSKScraper
        return MandarinHSKScraper()
    else:
        from scraper.generic_scraper import GenericScraper
        return GenericScraper()


def render():
    st.header("Content Generation")

    newsletters = get_newsletters()
    if not newsletters:
        st.warning("No newsletters found. Create one in Tab 1 first.")
        return

    nl_map = {f"{n['name']} ({n['language']} / {n['exam']})": n for n in newsletters}
    selected_nl_label = st.selectbox("Select Newsletter", list(nl_map.keys()), key="content_nl_select")
    nl = nl_map[selected_nl_label]

    # Derive exam key
    exam_key = None
    for k, cfg in EXAM_CONFIGS.items():
        if cfg.language == nl["language"] and cfg.exam == nl["exam"]:
            exam_key = k
            break
    if exam_key is None:
        exam_key = "custom"

    levels = get_levels_for_exam(exam_key)

    # ===========================================================
    # PHASE 1: Scrape & Index
    # ===========================================================
    st.subheader("Phase 1 — Scrape & Index")

    with st.expander("Scrape content from the web", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            level = st.selectbox("Level", levels, key="scrape_level")
        with col2:
            content_type = st.selectbox("Content Type", CONTENT_TYPES, key="scrape_content_type")
        with col3:
            # Show current index size — use the same name derivation as get_language_collection
            _coll = get_language_collection(nl["language"], nl["exam"])
            collection_name = _coll.name
            count = _coll.count()
            st.metric("Indexed Chunks", count)

        if st.button("Scrape & Index", type="primary"):
            with st.spinner("Scraping and indexing content..."):
                try:
                    scraper = _get_scraper(exam_key)

                    # Scrape
                    if exam_key == "custom":
                        raw_chunks = scraper.scrape(
                            url="",
                            language=nl["language"],
                            level=level,
                            content_type=content_type,
                        )
                    else:
                        raw_chunks = scraper.scrape(
                            url="",
                            level=level,
                            content_type=content_type,
                        )

                    if not raw_chunks:
                        st.warning(
                            "No chunks scraped. The target site may be blocking requests "
                            "or have changed its structure. Check the app logs for details. "
                            "If Playwright is installed (`playwright install chromium`), "
                            "it was tried automatically as a fallback."
                        )
                        return

                    # Add chroma_doc_id to each chunk
                    for chunk in raw_chunks:
                        chunk["chroma_doc_id"] = make_chunk_id(
                            chunk["source_url"], chunk["chunk_index"]
                        )

                    # Group by source URL for session tracking
                    url_groups: dict = {}
                    for chunk in raw_chunks:
                        url_groups.setdefault(chunk["source_url"], []).append(chunk)

                    all_sqlite_ids = []
                    for source_url, url_chunks in url_groups.items():
                        session_id = insert_scrape_session(
                            newsletter_id=nl["id"],
                            language=nl["language"],
                            exam=nl["exam"],
                            level=level,
                            content_type=content_type,
                            source_url=source_url,
                        )
                        for chunk in url_chunks:
                            chunk["session_id"] = session_id

                        # Insert chunks to SQLite
                        sqlite_ids = insert_chunks(url_chunks)
                        all_sqlite_ids.extend(sqlite_ids)

                        update_scrape_session(
                            session_id,
                            chunk_count=len(url_chunks),
                            status="scraped",
                        )

                    # Embed & upsert to ChromaDB
                    st.info("Embedding chunks into vector store...")
                    collection = get_language_collection(nl["language"], nl["exam"])
                    doc_ids = embed_and_upsert(raw_chunks, collection, all_sqlite_ids)
                    mark_chunks_embedded(all_sqlite_ids)

                    st.success(
                        f"Indexed **{len(raw_chunks)}** chunks from "
                        f"**{len(url_groups)}** source(s) into vector store."
                    )
                    st.rerun()

                except Exception as exc:
                    log.error("Scrape & index error: %s", exc)
                    import requests as _req
                    if isinstance(exc, _req.HTTPError) and exc.response is not None:
                        st.error(
                            f"HTTP {exc.response.status_code} from the target site. "
                            "The site may be blocking automated requests. "
                            "Playwright fallback will run automatically on the next attempt."
                        )
                    else:
                        st.error(f"Error during scraping: {exc}")

    # ===========================================================
    # PHASE 2: Generate Content
    # ===========================================================
    st.subheader("Phase 2 — Generate Content")

    with st.form("generate_form"):
        col1, col2 = st.columns(2)
        with col1:
            gen_level = st.selectbox("Level", levels, key="gen_level")
            theme = st.text_input(
                "Theme / Topic",
                placeholder="e.g. ordering food at a restaurant",
            )
        with col2:
            content_format = st.selectbox("Content Format", CONTENT_FORMATS, key="gen_content_format")
            auto_title = st.checkbox("Auto-generate title", value=True)

        generate_btn = st.form_submit_button("Generate Content", type="primary")

    if generate_btn:
        if not theme.strip():
            st.error("Please enter a theme/topic.")
            return

        # Check we have indexed content
        count = collection_count(collection_name)
        if count == 0:
            st.error(
                "No content indexed yet. Run Scrape & Index first."
            )
            return

        # Retrieve chunks
        with st.spinner("Retrieving relevant content from vector store..."):
            grammar_chunks, vocab_chunks = retrieve_for_generation(
                nl["language"], nl["exam"], gen_level, theme
            )

        if not grammar_chunks and not vocab_chunks:
            st.warning(
                "No relevant chunks found for this level/theme. "
                "Try scraping more content or changing the theme."
            )

        # Stream generation
        st.subheader("Generated Content")
        content_placeholder = st.empty()
        full_content = ""

        with st.spinner("Generating with Claude..."):
            try:
                for chunk in stream_content(
                    language=nl["language"],
                    exam=nl["exam"],
                    level=gen_level,
                    theme=theme,
                    content_format=content_format,
                    grammar_chunks=grammar_chunks,
                    vocab_chunks=vocab_chunks,
                ):
                    full_content += chunk
                    content_placeholder.markdown(full_content)
            except Exception as exc:
                st.error(f"Generation error: {exc}")
                return

        # Generate title
        post_title = theme.title()
        if auto_title:
            with st.spinner("Generating title..."):
                try:
                    post_title = generate_title(full_content, nl["language"], gen_level)
                except Exception:
                    pass

        st.text_input("Post Title", value=post_title, key="post_title_input")

        # Edit area
        edited_content = st.text_area(
            "Edit content before publishing",
            value=full_content,
            height=400,
            key="edited_content",
        )

        # Retrieve IDs for provenance
        retrieval_ids = get_retrieval_ids(nl["language"], nl["exam"], gen_level, theme)

        # Save draft to DB
        post_id = insert_generated_post(
            newsletter_id=nl["id"],
            title=post_title,
            content_type=content_format,
            language=nl["language"],
            exam=nl["exam"],
            level=gen_level,
            grammar_focus=", ".join(grammar_chunks[:2])[:200] if grammar_chunks else None,
            vocab_focus=", ".join(vocab_chunks[:2])[:200] if vocab_chunks else None,
            content_raw=full_content,
            retrieval_ids=json.dumps(retrieval_ids),
        )
        st.session_state["last_post_id"] = post_id
        st.info(f"Draft saved to database (ID: {post_id})")

        # Download as Markdown
        final_title = st.session_state.get("post_title_input", post_title)
        final_content = st.session_state.get("edited_content", full_content)
        from utils.helpers import slugify
        filename = f"{slugify(final_title)}.md"
        st.download_button(
            label="Download as Markdown",
            data=final_content,
            file_name=filename,
            mime="text/markdown",
        )

    # ===========================================================
    # Previous Content Browser
    # ===========================================================
    st.divider()
    st.subheader("Previous Content")

    posts = get_generated_posts(nl["id"])
    if not posts:
        st.info("No posts generated yet for this newsletter.")
    else:
        import pandas as pd
        from utils.helpers import slugify

        # ── Filters ────────────────────────────────────────────
        all_levels = sorted({p["level"] for p in posts if p.get("level")})
        all_formats = sorted({p["content_type"] for p in posts if p.get("content_type")})

        fcol1, fcol2, fcol3 = st.columns([2, 2, 3])
        with fcol1:
            filter_level = st.selectbox(
                "Filter by level",
                ["All"] + all_levels,
                key="browse_filter_level",
            )
        with fcol2:
            filter_format = st.selectbox(
                "Filter by format",
                ["All"] + all_formats,
                key="browse_filter_format",
            )
        with fcol3:
            search_query = st.text_input(
                "Search titles",
                placeholder="Type to filter…",
                key="browse_search",
            )

        filtered = posts
        if filter_level != "All":
            filtered = [p for p in filtered if p.get("level") == filter_level]
        if filter_format != "All":
            filtered = [p for p in filtered if p.get("content_type") == filter_format]
        if search_query.strip():
            q = search_query.strip().lower()
            filtered = [p for p in filtered if q in (p.get("title") or "").lower()]

        st.caption(f"{len(filtered)} of {len(posts)} posts")

        if not filtered:
            st.info("No posts match the current filters.")
        else:
            # ── Summary table ───────────────────────────────────
            df = pd.DataFrame(filtered)[["id", "level", "content_type", "title", "created_at"]]
            df.columns = ["ID", "Level", "Format", "Title", "Created"]
            df["Created"] = df["Created"].str[:10]
            st.dataframe(df, use_container_width=True, hide_index=True)

            # ── Post viewer ─────────────────────────────────────
            st.markdown("**View post**")
            post_labels = [
                f"[{p['level']}] {p['title']}  ({(p['created_at'] or '')[:10]})"
                for p in filtered
            ]
            chosen_label = st.selectbox(
                "Select a post to read",
                post_labels,
                key="browse_post_select",
                label_visibility="collapsed",
            )
            chosen_post = filtered[post_labels.index(chosen_label)]

            with st.container(border=True):
                meta_col1, meta_col2, meta_col3, meta_col4 = st.columns(4)
                meta_col1.metric("Language", chosen_post.get("language", "—"))
                meta_col2.metric("Level", chosen_post.get("level", "—"))
                meta_col3.metric("Format", chosen_post.get("content_type", "—"))
                meta_col4.metric("Post ID", chosen_post["id"])

                st.markdown(f"### {chosen_post.get('title', '(no title)')}")

                content = chosen_post.get("content_raw") or ""
                if content:
                    st.markdown(content)
                else:
                    st.info("No content stored for this post.")

                if content:
                    st.download_button(
                        label="Download as Markdown",
                        data=content,
                        file_name=f"{slugify(chosen_post.get('title', 'post'))}.md",
                        mime="text/markdown",
                        key="browse_download",
                    )
