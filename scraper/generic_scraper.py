"""Generic scraper for user-defined languages: Wiktionary + Wikipedia grammar."""
import re
from typing import List

from scraper.base_scraper import BaseScraper
from utils.logger import get_logger

log = get_logger(__name__)

WIKTIONARY_URL = "https://en.wiktionary.org/wiki/Wiktionary:Frequency_lists/{lang}"
WIKIPEDIA_GRAMMAR_URL = "https://en.wikipedia.org/wiki/{lang}_grammar"


class GenericScraper(BaseScraper):
    def scrape_grammar(self, language: str, level: str) -> List[dict]:
        lang_slug = language.replace(" ", "_")
        url = WIKIPEDIA_GRAMMAR_URL.format(lang=lang_slug)
        soup = self.get_soup(url)
        if soup is None:
            return []

        chunks = []
        # Extract sections from Wikipedia article
        content = soup.find("div", {"id": "mw-content-text"})
        if not content:
            return []

        sections = content.find_all(["h2", "h3"])
        for i, section in enumerate(sections[:20]):
            title = section.get_text(strip=True).replace("[edit]", "")
            body_parts = []
            sibling = section.find_next_sibling()
            while sibling and sibling.name not in ["h2", "h3"]:
                text = sibling.get_text(separator=" ", strip=True)
                if text:
                    body_parts.append(text)
                sibling = sibling.find_next_sibling()

            body = " ".join(body_parts)[:800]
            if len(body) < 50:
                continue

            chunks.append({
                "language": language,
                "exam": "Custom",
                "level": level,
                "content_type": "grammar",
                "source_url": url,
                "chunk_text": f"Grammar: {title}\n{body}",
                "chunk_index": i,
                "grammar_point": title,
            })
        log.info("%s grammar: %d chunks", language, len(chunks))
        return chunks

    def scrape_vocabulary(self, language: str, level: str) -> List[dict]:
        lang_slug = language.replace(" ", "_")
        url = WIKTIONARY_URL.format(lang=lang_slug)
        soup = self.get_soup(url)
        if soup is None:
            return []

        chunks = []
        words = []
        for link in soup.select("li a"):
            w = link.get_text(strip=True)
            if w and 2 < len(w) < 30:
                words.append(w)
            if len(words) >= 200:
                break

        for i in range(0, len(words), 10):
            batch = words[i:i + 10]
            if batch:
                chunks.append({
                    "language": language,
                    "exam": "Custom",
                    "level": level,
                    "content_type": "vocabulary",
                    "source_url": url,
                    "chunk_text": "Vocabulary:\n" + "\n".join(batch),
                    "chunk_index": i // 10,
                    "grammar_point": None,
                })
        log.info("%s vocabulary: %d chunks", language, len(chunks))
        return chunks

    def scrape(self, url: str = "", language: str = "German",
               level: str = "B1", content_type: str = "both") -> List[dict]:
        chunks = []
        if content_type in ("grammar", "both"):
            chunks.extend(self.scrape_grammar(language, level))
        if content_type in ("vocabulary", "both"):
            chunks.extend(self.scrape_vocabulary(language, level))
        return chunks
