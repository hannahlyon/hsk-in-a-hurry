# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
pip install -r requirements.txt
playwright install chromium

# Launch
streamlit run app.py
```

All imports use the project root on `sys.path` (inserted in `app.py`), so run Streamlit from the project root, never from a subdirectory.

## Environment

Copy `.env.example` → `.env` and fill in:
- `ANTHROPIC_API_KEY` — Claude API
- `OPENAI_API_KEY` — embeddings (text-embedding-3-small)
- `SUBSTACK_COOKIE` — optional default; users can also paste it in the sidebar at runtime (used by Analytics tab only)

`config/settings.py` loads `.env` and exposes all constants (model names, delays, thresholds, data paths). This is the single source of truth — do not hardcode model names or file paths elsewhere.

## Architecture

The app is a three-tab Streamlit dashboard. Each tab is a module in `tabs/` with a single `render()` function called from `app.py`. The sidebar manages the Substack session cookie via `st.session_state["substack_cookie"]`, which the Analytics tab reads.

| Tab | Module | Purpose |
|---|---|---|
| ⚙️ Newsletter Setup | `tabs/tab_create.py` | Create newsletters (name, language, exam, optional Substack URL) |
| ✍️ Content Generation | `tabs/tab_content.py` | Scrape, index, generate, download as Markdown |
| 📊 Analytics | `tabs/tab_analytics.py` | Fetch stats from Substack read-only API via cookie |

### Data flow for content generation (Tab 2)

```
Scraper → SQLite (scraped_chunks) → vector_store (embedded)
                                          ↓
Theme + filters → retriever.py → grammar chunks + vocab chunks
                                          ↓
                              rag/generator.py (Claude streaming)
                                          ↓
                         "Download as Markdown" button
```

1. **Scraping**: `scraper/base_scraper.py` provides rate-limiting (1.5–4s random delay), robots.txt, and a 7-day HTML cache keyed by `sha256(url)` in `data/scrape_cache/`. Each language has its own scraper class; they all return a list of chunk dicts with keys: `language`, `exam`, `level`, `content_type`, `source_url`, `chunk_text`, `chunk_index`, `grammar_point`.

2. **Indexing**: `vector_store/embedder.py` embeds chunks via OpenAI in batches of 100, then upserts using a deterministic ID = `sha256(source_url + str(chunk_index))[:16]` — re-scraping the same URL is always a safe no-op.

3. **Vector store** (`vector_store/chroma_client.py`) is a SQLite + numpy implementation — **not ChromaDB**. ChromaDB was removed due to an irreconcilable pydantic v1/v2 conflict with `anthropic` and `openai`. Embeddings are stored as float32 BLOBs in the `vector_store` table of `data/newsletters.db`. The `Collection` class in `chroma_client.py` exposes the same `.count()`, `.upsert()`, and `.query()` interface that the rest of the codebase uses. Collections are named `lang_{language}_{exam}` (slugified, lowercase). The `where` filter supports ChromaDB's `$and`/`$eq` syntax.

4. **Retrieval**: `rag/retriever.py` runs two separate queries per generation request — grammar (n=4) and vocabulary (n=6) — both filtered to the exact `language + exam + level`. Deduplication uses Jaccard similarity as a proxy.

5. **Generation**: `rag/generator.py` calls Claude (`claude-sonnet-4-6`) using the prompt templates in `rag/prompts.py`. Use `stream_content()` in the UI (yields chunks) or `generate_content()` for non-streaming.

6. **Export**: Generated content is saved as a draft in SQLite and can be downloaded as a `.md` file via `st.download_button`.

### Database

SQLite at `data/newsletters.db`, initialised on startup via `database/db.py:init_db()` (idempotent). All CRUD is in `database/db.py` — no ORM, raw `sqlite3` with `row_factory = sqlite3.Row`. The schema is in `database/schema.sql`.

Key relationships: `newsletters` → `generated_posts`. Scraping writes to `scrape_sessions` + `scraped_chunks`. Analytics writes to `analytics_snapshots` + `post_analytics`.

### Adding a new language

1. Add an `ExamConfig` entry to `config/languages.py` (`EXAM_CONFIGS` dict).
2. Add the display name to `LANGUAGE_OPTIONS`.
3. Create `scraper/{language_slug}.py` extending `BaseScraper`; implement `scrape_grammar()`, `scrape_vocabulary()`, and `scrape()`.
4. Add a branch for the new exam key in `tabs/tab_content.py:_get_scraper()`.

### Substack auth (Analytics only)

`substack/auth.py:build_session()` parses a raw browser Cookie header string (semicolon-separated `name=value` pairs) into a `requests.Session`. All Substack API calls raise `SubstackAuthError` on HTTP 401/403. The Substack internal API endpoints are defined as module-level constants in `substack/analytics.py` — update them there if Substack changes URLs.

## Key Constants (config/settings.py)

| Constant | Default | Purpose |
|---|---|---|
| `CLAUDE_MODEL` | `claude-sonnet-4-6` | All text generation |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI embeddings (stored in SQLite) |
| `GRAMMAR_RETRIEVAL_N` | 4 | Chunks retrieved per generation |
| `VOCAB_RETRIEVAL_N` | 6 | Chunks retrieved per generation |
| `MMR_SIMILARITY_THRESHOLD` | 0.92 | Dedup cutoff in retriever |
| `SCRAPE_CACHE_TTL_DAYS` | 7 | HTML cache expiry |

## Dependency Constraints

- **ChromaDB is not used.** Every version of ChromaDB (0.4.x and 0.5.x) triggers `pydantic.v1.errors.ConfigError` in this stack because `anthropic`/`openai` install pydantic v2, which causes ChromaDB to fall back to a broken `pydantic.v1` shim. The vector store is implemented in `vector_store/chroma_client.py` using SQLite + numpy instead.
- **`python-substack` is not used.** Publishing via Substack's internal API proved unreliable. The package has been removed; content is exported as Markdown instead. This also resolved the former `python-dotenv<0.22.0` pin — `python-dotenv>=1.0.0` is now used.
