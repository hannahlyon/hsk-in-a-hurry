"""HSK Mandarin scraper — digmandarin.com (grammar) + hsk.academy (vocabulary)."""
import re
from typing import List

from scraper.base_scraper import BaseScraper
from utils.logger import get_logger

log = get_logger(__name__)

# digmandarin.com has per-level grammar pages for HSK 1–6
GRAMMAR_URL = "https://www.digmandarin.com/hsk-{level_num}-grammar"
# hsk.academy corrected URL pattern (found from their homepage links)
VOCAB_URL = "https://hsk.academy/en/hsk-{level_num}-vocabulary-list"

# New HSK 7–9 map to HSK 6 grammar (highest available)
_MAX_GRAMMAR_LEVEL = 6


def _level_num(level: str) -> str:
    """Extract numeric part from e.g. 'HSK3' → '3'. Clamps to 1–6 for grammar."""
    return re.sub(r"[^0-9]", "", level) or "1"


def _clamp(n: str, lo: int, hi: int) -> str:
    return str(max(lo, min(hi, int(n))))


class MandarinHSKScraper(BaseScraper):

    def scrape_grammar(self, level: str) -> List[dict]:
        """Scrape HSK grammar points from digmandarin.com."""
        num = _level_num(level)
        clamped = _clamp(num, 1, _MAX_GRAMMAR_LEVEL)
        url = GRAMMAR_URL.format(level_num=clamped)

        soup = self.get_soup(url)
        if soup is None:
            return []

        article = soup.find("article") or soup.find("main")
        if article is None:
            log.warning("digmandarin: no <article> found at %s", url)
            return []

        full_text = article.get_text(separator="\n", strip=True)

        # Split by numbered section headers like "3.1 – The Summary of…" or "1.1: How to…"
        # HSK1 uses colons; HSK2–6 use dashes/em-dashes
        section_pattern = re.compile(
            r"(?=\n?\d+\.\d+\s*[–—:\-]\s*)", re.MULTILINE
        )
        parts = section_pattern.split(full_text)

        # First part is the table of contents / intro — skip it
        sections = [p.strip() for p in parts[1:] if p.strip()]

        chunks = []
        for i, section in enumerate(sections):
            # Extract grammar point name from first line
            lines = section.split("\n")
            header = lines[0].strip()
            body = "\n".join(lines[1:]).strip()

            # Skip very short sections (navigation noise)
            if len(body) < 40:
                continue

            chunk_text = f"Grammar: {header}\n{body[:900]}"
            chunks.append({
                "language": "Mandarin Chinese",
                "exam": "HSK",
                "level": level,
                "content_type": "grammar",
                "source_url": url,
                "chunk_text": chunk_text,
                "chunk_index": i,
                "grammar_point": header,
            })

        log.info("HSK %s grammar: %d chunks from %s", level, len(chunks), url)
        return chunks

    def scrape_vocabulary(self, level: str) -> List[dict]:
        """Scrape HSK vocabulary from hsk.academy."""
        num = _level_num(level)
        url = VOCAB_URL.format(level_num=num)

        soup = self.get_soup(url)
        if soup is None:
            return []

        # Table has no header row; columns: [word+pinyin combined, meaning]
        table = soup.find("table")
        if not table:
            log.warning("hsk.academy: no table found at %s", url)
            return []

        entries = []
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            word_pinyin = cells[0].get_text(strip=True)
            meaning = cells[1].get_text(strip=True)
            if word_pinyin and meaning:
                entries.append(f"{word_pinyin}: {meaning}")

        chunks = []
        batch_size = 10
        for i in range(0, len(entries), batch_size):
            batch = entries[i : i + batch_size]
            if batch:
                chunks.append({
                    "language": "Mandarin Chinese",
                    "exam": "HSK",
                    "level": level,
                    "content_type": "vocabulary",
                    "source_url": url,
                    "chunk_text": "Vocabulary:\n" + "\n".join(batch),
                    "chunk_index": i // batch_size,
                    "grammar_point": None,
                })

        log.info("HSK %s vocabulary: %d chunks (%d words) from %s",
                 level, len(chunks), len(entries), url)
        return chunks

    def scrape(self, url: str = "", level: str = "HSK3",
               content_type: str = "both") -> List[dict]:
        chunks = []
        if content_type in ("grammar", "both"):
            chunks.extend(self.scrape_grammar(level))
        if content_type in ("vocabulary", "both"):
            chunks.extend(self.scrape_vocabulary(level))
        return chunks
