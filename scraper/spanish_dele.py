"""DELE Spanish scraper — spanishgrammar.net + Wiktionary."""
import re
from typing import List
from bs4 import BeautifulSoup

from scraper.base_scraper import BaseScraper
from utils.logger import get_logger

log = get_logger(__name__)

GRAMMAR_URL = "https://www.spanishgrammar.net/category/dele/{level}/"
WIKTIONARY_VOCAB_URL = "https://en.wiktionary.org/wiki/Wiktionary:Frequency_lists/Spanish"


class SpanishDELEScraper(BaseScraper):
    def scrape_grammar(self, level: str) -> List[dict]:
        url = GRAMMAR_URL.format(level=level.lower())
        soup = self.get_soup(url)
        if soup is None:
            return []

        chunks = []
        articles = soup.find_all("article") or soup.find_all("div", class_="post")
        for i, article in enumerate(articles):
            title_el = article.find(["h1", "h2", "h3"])
            title = title_el.get_text(strip=True) if title_el else f"Grammar entry {i}"
            body = article.get_text(separator=" ", strip=True)
            if len(body) < 50:
                continue
            chunk_text = f"Grammar: {title}\n{body[:800]}"
            chunks.append({
                "language": "Spanish",
                "exam": "DELE",
                "level": level,
                "content_type": "grammar",
                "source_url": url,
                "chunk_text": chunk_text,
                "chunk_index": i,
                "grammar_point": title,
            })

        log.info("DELE %s grammar: %d chunks", level, len(chunks))
        return chunks

    def scrape_vocabulary(self, level: str) -> List[dict]:
        """Scrape Wiktionary Spanish frequency list (level-agnostic)."""
        soup = self.get_soup(WIKTIONARY_VOCAB_URL)
        if soup is None:
            return []

        chunks = []
        words = []
        for link in soup.select("li a[title]"):
            w = link.get_text(strip=True)
            if w and re.match(r"^[a-záéíóúüñ\s]+$", w, re.IGNORECASE):
                words.append(w)
            if len(words) >= 200:
                break

        for i in range(0, len(words), 10):
            batch = words[i:i + 10]
            if batch:
                chunks.append({
                    "language": "Spanish",
                    "exam": "DELE",
                    "level": level,
                    "content_type": "vocabulary",
                    "source_url": WIKTIONARY_VOCAB_URL,
                    "chunk_text": "Vocabulary:\n" + "\n".join(batch),
                    "chunk_index": i // 10,
                    "grammar_point": None,
                })
        log.info("DELE %s vocabulary: %d chunks", level, len(chunks))
        return chunks

    def scrape(self, url: str = "", level: str = "B1",
               content_type: str = "both") -> List[dict]:
        chunks = []
        if content_type in ("grammar", "both"):
            chunks.extend(self.scrape_grammar(level))
        if content_type in ("vocabulary", "both"):
            chunks.extend(self.scrape_vocabulary(level))
        return chunks
