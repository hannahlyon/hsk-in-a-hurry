"""TOPIK Korean scraper — topikguide.com + Wiktionary."""
import re
from typing import List

from scraper.base_scraper import BaseScraper
from utils.logger import get_logger

log = get_logger(__name__)

GRAMMAR_URL_TOPIK1 = "https://topikguide.com/topik-grammar/topik-1-grammar/"
GRAMMAR_URL_TOPIK2 = "https://topikguide.com/topik-grammar/topik-2-grammar/"
WIKTIONARY_VOCAB_URL = "https://en.wiktionary.org/wiki/Wiktionary:Frequency_lists/Korean"

HANGUL_RE = re.compile(r"[\uAC00-\uD7A3]")

# Levels 1–2 use TOPIK I material; 3–6 use TOPIK II
_TOPIK1_LEVELS = {"Level 1", "Level 2"}


def _grammar_url_for_level(level: str) -> str:
    return GRAMMAR_URL_TOPIK1 if level in _TOPIK1_LEVELS else GRAMMAR_URL_TOPIK2


class KoreanTOPIKScraper(BaseScraper):
    def scrape_grammar(self, level: str) -> List[dict]:
        url = _grammar_url_for_level(level)
        soup = self.get_soup(url)
        if soup is None:
            return []

        chunks = []

        # Primary: article or entry-content blocks
        entries = (
            soup.find_all("article")
            or soup.find_all("div", class_="entry-content")
        )

        if entries:
            for i, entry in enumerate(entries):
                heading = entry.find(["h2", "h3"])
                grammar_point = heading.get_text(strip=True) if heading else f"Grammar entry {i}"
                body = entry.get_text(separator=" ", strip=True)
                if len(body) < 40:
                    continue
                chunk_text = f"Grammar: {grammar_point}\n{body[:800]}"
                chunks.append({
                    "language": "Korean",
                    "exam": "TOPIK",
                    "level": level,
                    "content_type": "grammar",
                    "source_url": url,
                    "chunk_text": chunk_text,
                    "chunk_index": i,
                    "grammar_point": grammar_point,
                })
        else:
            # Fallback: scan paragraphs and list items containing Hangul
            fallback_items = [
                el for el in soup.find_all(["p", "li"])
                if HANGUL_RE.search(el.get_text())
            ]
            for i, el in enumerate(fallback_items):
                text = el.get_text(separator=" ", strip=True)
                if len(text) < 40:
                    continue
                chunks.append({
                    "language": "Korean",
                    "exam": "TOPIK",
                    "level": level,
                    "content_type": "grammar",
                    "source_url": url,
                    "chunk_text": f"Grammar: {text[:800]}",
                    "chunk_index": i,
                    "grammar_point": text[:80],
                })

        log.info("TOPIK %s grammar: %d chunks from %s", level, len(chunks), url)
        return chunks

    def scrape_vocabulary(self, level: str) -> List[dict]:
        """Scrape Wiktionary Korean frequency list (level-agnostic)."""
        soup = self.get_soup(WIKTIONARY_VOCAB_URL)
        if soup is None:
            return []

        words = []

        # Primary: linked words in list items
        for link in soup.select("li a"):
            w = link.get_text(strip=True)
            if w and HANGUL_RE.search(w):
                words.append(w)
            if len(words) >= 200:
                break

        # Fallback: any list item text containing Hangul
        if not words:
            for li in soup.find_all("li"):
                text = li.get_text(strip=True)
                if HANGUL_RE.search(text):
                    words.append(text[:60])
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

        log.info("TOPIK %s vocabulary: %d chunks", level, len(chunks))
        return chunks

    def scrape(self, url: str = "", level: str = "Level 3",
               content_type: str = "both") -> List[dict]:
        chunks = []
        if content_type in ("grammar", "both"):
            chunks.extend(self.scrape_grammar(level))
        if content_type in ("vocabulary", "both"):
            chunks.extend(self.scrape_vocabulary(level))
        return chunks
