"""DELF/DALF French scraper — french-exam.com + 1000mostcommonwords.com."""
import re
from typing import List

from scraper.base_scraper import BaseScraper
from utils.logger import get_logger

log = get_logger(__name__)

# URL changed from /category/delf-dalf/{level}/ to /category/delf-dalf-exam-preparation/delf-{level}/
# C1 and C2 share the same page on this site.
_GRAMMAR_URLS = {
    "A1": "https://www.french-exam.com/category/delf-dalf-exam-preparation/delf-a1/",
    "A2": "https://www.french-exam.com/category/delf-dalf-exam-preparation/delf-a2/",
    "B1": "https://www.french-exam.com/category/delf-dalf-exam-preparation/delf-b1/",
    "B2": "https://www.french-exam.com/category/delf-dalf-exam-preparation/delf-b2/",
    "C1": "https://www.french-exam.com/category/delf-dalf-exam-preparation/delf-c1-c2/",
    "C2": "https://www.french-exam.com/category/delf-dalf-exam-preparation/delf-c1-c2/",
}

_VOCAB_URL = "https://www.1000mostcommonwords.com/1000-most-common-french-words/"

# Word-rank bands per CEFR level (1-indexed rows from the frequency table)
_LEVEL_BANDS = {
    "A1": (1,   200),
    "A2": (201, 400),
    "B1": (401, 600),
    "B2": (601, 800),
    "C1": (801, 900),
    "C2": (901, 1000),
}


class FrenchDELFScraper(BaseScraper):
    def scrape_grammar(self, level: str) -> List[dict]:
        url = _GRAMMAR_URLS.get(level.upper())
        if not url:
            log.warning("No grammar URL configured for level %s", level)
            return []

        soup = self.get_soup(url)
        if soup is None:
            return []

        chunks = []
        articles = soup.find_all("article") or soup.find_all("div", class_="post")
        for i, article in enumerate(articles):
            title_el = article.find(["h1", "h2", "h3"])
            title = title_el.get_text(strip=True) if title_el else f"Grammar {i}"
            body = article.get_text(separator=" ", strip=True)
            if len(body) < 50:
                continue
            chunks.append({
                "language": "French",
                "exam": "DELF/DALF",
                "level": level,
                "content_type": "grammar",
                "source_url": url,
                "chunk_text": f"Grammar: {title}\n{body[:800]}",
                "chunk_index": i,
                "grammar_point": title,
            })
        log.info("DELF %s grammar: %d chunks from %s", level, len(chunks), url)
        return chunks

    def scrape_vocabulary(self, level: str) -> List[dict]:
        soup = self.get_soup(_VOCAB_URL)
        if soup is None:
            return []

        # Parse the frequency table: Number | French | English
        rows = []
        table = soup.find("table")
        if table:
            for tr in table.find_all("tr")[1:]:  # skip header
                cells = tr.find_all("td")
                if len(cells) >= 3:
                    french = cells[1].get_text(strip=True)
                    english = cells[2].get_text(strip=True)
                    if french and english:
                        rows.append(f"{french} — {english}")

        start, end = _LEVEL_BANDS.get(level.upper(), (1, 200))
        # rows list is 0-indexed, bands are 1-indexed
        band = rows[start - 1 : end]

        chunks = []
        for i, batch_start in enumerate(range(0, len(band), 10)):
            batch = band[batch_start : batch_start + 10]
            if not batch:
                continue
            # Use level in source_url to ensure unique chunk IDs across levels
            chunk_source = f"{_VOCAB_URL}#{level.lower()}"
            chunks.append({
                "language": "French",
                "exam": "DELF/DALF",
                "level": level,
                "content_type": "vocabulary",
                "source_url": chunk_source,
                "chunk_text": "Vocabulary:\n" + "\n".join(batch),
                "chunk_index": i,
                "grammar_point": None,
            })

        log.info("DELF %s vocabulary: %d chunks (words %d–%d)", level, len(chunks), start, end)
        return chunks

    def scrape(self, url: str = "", level: str = "B1",
               content_type: str = "both") -> List[dict]:
        chunks = []
        if content_type in ("grammar", "both"):
            chunks.extend(self.scrape_grammar(level))
        if content_type in ("vocabulary", "both"):
            chunks.extend(self.scrape_vocabulary(level))
        return chunks
