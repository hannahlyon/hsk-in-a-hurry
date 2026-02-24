"""JLPT scraper — jlptsensei.com grammar and vocabulary lists."""
import re
from typing import List
from bs4 import BeautifulSoup

from scraper.base_scraper import BaseScraper
from utils.logger import get_logger

log = get_logger(__name__)

GRAMMAR_URL = "https://jlptsensei.com/jlpt-{level}-grammar-list/"
VOCAB_URL = "https://jlptsensei.com/jlpt-{level}-vocabulary-list/"


class JLPTScraper(BaseScraper):
    def __init__(self):
        super().__init__()

    def scrape_grammar(self, level: str) -> List[dict]:
        """Scrape grammar list for a given JLPT level (N1–N5)."""
        url = GRAMMAR_URL.format(level=level.lower())
        soup = self.get_soup(url)
        if soup is None:
            return []

        chunks = []
        # Table id is "jl-grammar"; columns: #, Grammar Lesson (romaji), 文法 (Japanese), Meaning
        table = soup.find("table", {"id": "jl-grammar"}) or \
                soup.find("table", class_=lambda c: c and "jl-table" in (c if isinstance(c, list) else [c]))

        if table:
            rows = table.find_all("tr")[1:]  # skip header
            for i, row in enumerate(rows):
                cells = row.find_all(["td", "th"])
                if len(cells) < 4:
                    continue
                grammar_point = cells[1].get_text(strip=True)  # romaji name
                japanese = cells[2].get_text(strip=True)       # Japanese form
                meaning = cells[3].get_text(strip=True)        # English meaning
                if not grammar_point:
                    continue
                chunk_text = f"Grammar: {grammar_point} ({japanese})\nMeaning: {meaning}"
                chunks.append({
                    "language": "Japanese",
                    "exam": "JLPT",
                    "level": level,
                    "content_type": "grammar",
                    "source_url": url,
                    "chunk_text": chunk_text,
                    "chunk_index": i,
                    "grammar_point": grammar_point,
                })
        else:
            # Fallback: extract all text blocks that look like grammar entries
            chunks = self._parse_fallback_grammar(soup, url, level)

        log.info("JLPT %s grammar: %d chunks scraped", level, len(chunks))
        return chunks

    def scrape_vocabulary(self, level: str) -> List[dict]:
        """Scrape vocabulary list for a given JLPT level."""
        url = VOCAB_URL.format(level=level.lower())
        soup = self.get_soup(url)
        if soup is None:
            return []

        chunks = []
        # Table id is "jl-vocab"; columns: #, 語彙 (Japanese), Vocabulary (romaji+reading), Type, Meaning
        table = soup.find("table", {"id": "jl-vocab"}) or \
                soup.find("table", class_=lambda c: c and "jl-table" in (c if isinstance(c, list) else [c]))

        if table:
            rows = table.find_all("tr")[1:]
            # Batch vocab into groups of 10
            batch_size = 10
            for batch_start in range(0, len(rows), batch_size):
                batch = rows[batch_start:batch_start + batch_size]
                entries = []
                for row in batch:
                    cells = row.find_all(["td", "th"])
                    if len(cells) < 5:
                        continue
                    japanese = cells[1].get_text(strip=True)      # kanji/kana form
                    reading = cells[2].get_text(strip=True)       # romaji + reading
                    meaning = cells[4].get_text(strip=True)       # English meaning
                    if japanese:
                        entries.append(f"{japanese} ({reading}): {meaning}")
                if entries:
                    chunk_text = "Vocabulary:\n" + "\n".join(entries)
                    chunks.append({
                        "language": "Japanese",
                        "exam": "JLPT",
                        "level": level,
                        "content_type": "vocabulary",
                        "source_url": url,
                        "chunk_text": chunk_text,
                        "chunk_index": batch_start // batch_size,
                        "grammar_point": None,
                    })
        else:
            chunks = self._parse_fallback_vocab(soup, url, level)

        log.info("JLPT %s vocabulary: %d chunks scraped", level, len(chunks))
        return chunks

    def _parse_fallback_grammar(self, soup: BeautifulSoup,
                                 url: str, level: str) -> List[dict]:
        """Fallback parser for changed page structure."""
        chunks = []
        items = soup.find_all("div", class_=lambda c: c and "grammar" in c.lower())
        for i, item in enumerate(items):
            text = item.get_text(separator=" ", strip=True)
            if len(text) > 20:
                chunks.append({
                    "language": "Japanese",
                    "exam": "JLPT",
                    "level": level,
                    "content_type": "grammar",
                    "source_url": url,
                    "chunk_text": text[:800],
                    "chunk_index": i,
                    "grammar_point": None,
                })
        return chunks

    def _parse_fallback_vocab(self, soup: BeautifulSoup,
                               url: str, level: str) -> List[dict]:
        """Fallback vocab parser."""
        chunks = []
        items = soup.find_all(["li", "p"])
        entries = []
        for item in items:
            text = item.get_text(strip=True)
            if re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", text) and len(text) > 5:
                entries.append(text)
        for i in range(0, len(entries), 10):
            batch = entries[i:i + 10]
            if batch:
                chunks.append({
                    "language": "Japanese",
                    "exam": "JLPT",
                    "level": level,
                    "content_type": "vocabulary",
                    "source_url": url,
                    "chunk_text": "Vocabulary:\n" + "\n".join(batch),
                    "chunk_index": i // 10,
                    "grammar_point": None,
                })
        return chunks

    def scrape(self, url: str, level: str = "N3",
               content_type: str = "both") -> List[dict]:
        chunks = []
        if content_type in ("grammar", "both"):
            chunks.extend(self.scrape_grammar(level))
        if content_type in ("vocabulary", "both"):
            chunks.extend(self.scrape_vocabulary(level))
        return chunks
