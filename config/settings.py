"""Centralised .env loader and app configuration."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
_ROOT = Path(__file__).parent.parent
load_dotenv(_ROOT / ".env")

ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
SUBSTACK_COOKIE: str = os.getenv("SUBSTACK_COOKIE", "")

# Data directories
DATA_DIR = Path(os.getenv("DATA_DIR", str(_ROOT / "data")))
DB_PATH = DATA_DIR / "newsletters.db"
SCRAPE_CACHE_DIR = DATA_DIR / "scrape_cache"
SOCIAL_IMAGES_DIR = DATA_DIR / "social_images"

# Ensure dirs exist
for _d in [DATA_DIR, SCRAPE_CACHE_DIR, SOCIAL_IMAGES_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# Model identifiers
CLAUDE_MODEL = "claude-sonnet-4-6"
EMBEDDING_MODEL = "text-embedding-3-small"
DALLE_MODEL = "dall-e-3"

# Scraper settings
SCRAPER_MIN_DELAY = 1.5
SCRAPER_MAX_DELAY = 4.0
SCRAPE_CACHE_TTL_DAYS = 7

# ChromaDB retrieval
GRAMMAR_RETRIEVAL_N = 4
VOCAB_RETRIEVAL_N = 6
MMR_SIMILARITY_THRESHOLD = 0.92
