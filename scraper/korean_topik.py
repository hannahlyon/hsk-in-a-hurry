"""TOPIK Korean scraper — topikguide.com + Wiktionary."""
import re
from typing import List

from scraper.base_scraper import BaseScraper
from utils.logger import get_logger

log = get_logger(__name__)

GRAMMAR_CATEGORY_URL = "https://www.topikguide.com/category/topik-grammar/"
WIKTIONARY_VOCAB_URL = "https://en.wiktionary.org/wiki/Wiktionary:Frequency_lists/Korean_5800"

HANGUL_RE = re.compile(r"[\uAC00-\uD7A3]")

# Levels 1–2 → TOPIK I; 3–6 → TOPIK II
_TOPIK1_LEVELS = {"Level 1", "Level 2"}


def _topik_tier(level: str) -> str:
    return "topik-i" if level in _TOPIK1_LEVELS else "topik-ii"


class KoreanTOPIKScraper(BaseScraper):
    def scrape_grammar(self, level: str) -> List[dict]:
        tier_tag = _topik_tier(level)  # "topik-i" or "topik-ii"
        soup = self.get_soup(GRAMMAR_CATEGORY_URL)
        if soup is None:
            return []

        chunks = []
        articles = soup.find_all("article")

        for i, article in enumerate(articles):
            classes = " ".join(article.get("class", []))
            # Include article if it matches the tier tag or has no tier tag at all
            has_topik1 = "tag-topik-i" in classes
            has_topik2 = "tag-topik-ii" in classes
            if tier_tag == "topik-i" and has_topik2 and not has_topik1:
                continue
            if tier_tag == "topik-ii" and has_topik1 and not has_topik2:
                continue

            h2 = article.find("h2")
            grammar_point = h2.get_text(strip=True) if h2 else f"Grammar entry {i}"

            # Prefer <p> excerpt over raw article text
            p = article.find("p")
            excerpt = p.get_text(separator=" ", strip=True) if p else article.get_text(separator=" ", strip=True)
            if len(excerpt) < 30:
                continue

            chunk_text = f"Grammar: {grammar_point}\n{excerpt[:800]}"
            chunks.append({
                "language": "Korean",
                "exam": "TOPIK",
                "level": level,
                "content_type": "grammar",
                "source_url": GRAMMAR_CATEGORY_URL,
                "chunk_text": chunk_text,
                "chunk_index": i,
                "grammar_point": grammar_point,
            })

        log.info("TOPIK %s grammar: %d chunks (tier: %s)", level, len(chunks), tier_tag)
        return chunks

    def scrape_vocabulary(self, level: str) -> List[dict]:
        """Scrape Wiktionary Korean 5800-word frequency list (level-agnostic)."""
        soup = self.get_soup(WIKTIONARY_VOCAB_URL)
        if soup is None:
            return []

        words = []
        body = soup.find("div", class_="mw-parser-output") or soup

        for a in body.find_all("a", href=True):
            word = a.get_text(strip=True)
            if word and HANGUL_RE.search(word) and len(word) <= 10:
                words.append(word)
            if len(words) >= 200:
                break

        chunks = []
        for i in range(0, len(words), 10):
            batch = words[i:i + 10]
            if batch:
                chunks.append({
                    "language": "Korean",
                    "exam": "TOPIK",
                    "level": level,
                    "content_type": "vocabulary",
                    "source_url": WIKTIONARY_VOCAB_URL,
                    "chunk_text": "Vocabulary:\n" + "\n".join(batch),
                    "chunk_index": i // 10,
                    "grammar_point": None,
                })

        log.info("TOPIK %s vocabulary: %d chunks (%d words)", level, len(chunks), len(words))
        return chunks

    def scrape(self, url: str = "", level: str = "Level 3",
               content_type: str = "both") -> List[dict]:
        chunks = []
        if content_type in ("grammar", "both"):
            chunks.extend(self.scrape_grammar(level))
        if content_type in ("vocabulary", "both"):
            chunks.extend(self.scrape_vocabulary(level))
        return chunks
