"""
Scrape, embed, and index all DELF/DALF levels (A1–C2) for French.

Usage (run from project root):
    python scripts/index_french.py                    # grammar + vocabulary, all levels
    python scripts/index_french.py --levels A1 B1     # specific levels only
    python scripts/index_french.py --type grammar     # grammar only
    python scripts/index_french.py --type vocabulary  # vocabulary only
    python scripts/index_french.py --dry-run          # scrape only, no embedding
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.languages import LEVELS_CEFR
from database.db import (
    init_db, get_newsletters, insert_newsletter,
    insert_scrape_session, update_scrape_session,
    insert_chunks, mark_chunks_embedded,
)
from scraper.french_delf import FrenchDELFScraper
from vector_store.chroma_client import get_language_collection
from vector_store.embedder import embed_and_upsert, make_chunk_id
from utils.logger import get_logger

log = get_logger("index_french")

LANGUAGE = "French"
EXAM = "DELF/DALF"


def _get_or_create_newsletter() -> dict:
    newsletters = get_newsletters()
    for nl in newsletters:
        if nl["language"] == LANGUAGE and nl["exam"] == EXAM:
            return nl
    nl_id = insert_newsletter(name="French DELF/DALF", language=LANGUAGE, exam=EXAM)
    log.info("Created newsletter id=%d", nl_id)
    newsletters = get_newsletters()
    return next(n for n in newsletters if n["id"] == nl_id)


def _index_level(nl: dict, level: str, content_type: str,
                 scraper: FrenchDELFScraper, collection,
                 dry_run: bool) -> dict:
    stats = {"level": level, "type": content_type, "scraped": 0, "embedded": 0, "error": None}

    try:
        raw_chunks = scraper.scrape(url="", level=level, content_type=content_type)
    except Exception as exc:
        stats["error"] = str(exc)
        log.error("Scrape failed for %s %s: %s", level, content_type, exc)
        return stats

    if not raw_chunks:
        log.warning("%s %s: no chunks returned", level, content_type)
        return stats

    stats["scraped"] = len(raw_chunks)

    for chunk in raw_chunks:
        chunk["chroma_doc_id"] = make_chunk_id(chunk["source_url"], chunk["chunk_index"])

    url_groups: dict = {}
    for chunk in raw_chunks:
        url_groups.setdefault(chunk["source_url"], []).append(chunk)

    all_sqlite_ids: list[int] = []
    for source_url, url_chunks in url_groups.items():
        session_id = insert_scrape_session(
            newsletter_id=nl["id"],
            language=LANGUAGE,
            exam=EXAM,
            level=level,
            content_type=content_type,
            source_url=source_url,
        )
        for chunk in url_chunks:
            chunk["session_id"] = session_id
        sqlite_ids = insert_chunks(url_chunks)
        all_sqlite_ids.extend(sqlite_ids)
        update_scrape_session(session_id, chunk_count=len(url_chunks), status="scraped")

    if dry_run:
        log.info("%s %s: dry-run, skipping embedding (%d chunks)", level, content_type, len(raw_chunks))
        return stats

    try:
        embed_and_upsert(raw_chunks, collection, all_sqlite_ids)
        mark_chunks_embedded(all_sqlite_ids)
        stats["embedded"] = len(raw_chunks)
    except Exception as exc:
        stats["error"] = str(exc)
        log.error("Embedding failed for %s %s: %s", level, content_type, exc)

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Index French DELF/DALF content into vector store")
    parser.add_argument(
        "--levels", nargs="+", default=LEVELS_CEFR,
        metavar="LEVEL",
        help="CEFR levels to index (default: all A1–C2)",
    )
    parser.add_argument(
        "--type", dest="content_type", default="both",
        choices=["grammar", "vocabulary", "both"],
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    init_db()
    nl = _get_or_create_newsletter()
    log.info("Using newsletter: %s (id=%d)", nl["name"], nl["id"])

    collection = get_language_collection(LANGUAGE, EXAM)
    scraper = FrenchDELFScraper()

    content_types = (
        ["grammar", "vocabulary"] if args.content_type == "both"
        else [args.content_type]
    )

    all_stats = []
    total_levels = len(args.levels)

    for i, level in enumerate(args.levels, 1):
        print(f"\n{'='*50}")
        print(f"  {level}  ({i}/{total_levels})")
        print(f"{'='*50}")

        for ct in content_types:
            print(f"  Scraping {ct}...", end=" ", flush=True)
            t0 = time.time()
            stats = _index_level(nl, level, ct, scraper, collection, args.dry_run)
            elapsed = time.time() - t0
            all_stats.append(stats)

            if stats["error"]:
                print(f"ERROR: {stats['error']}")
            elif stats["scraped"] == 0:
                print("no chunks found")
            elif args.dry_run:
                print(f"{stats['scraped']} chunks scraped (dry-run)  [{elapsed:.1f}s]")
            else:
                print(f"{stats['scraped']} chunks scraped, {stats['embedded']} embedded  [{elapsed:.1f}s]")

        if i < total_levels:
            time.sleep(1.5)

    print(f"\n{'='*50}")
    print("  SUMMARY")
    print(f"{'='*50}")
    total_scraped = sum(s["scraped"] for s in all_stats)
    total_embedded = sum(s["embedded"] for s in all_stats)
    errors = [s for s in all_stats if s["error"]]

    print(f"  Levels processed     : {total_levels}")
    print(f"  Total chunks scraped : {total_scraped}")
    if not args.dry_run:
        print(f"  Total chunks embedded: {total_embedded}")
    print(f"  Errors               : {len(errors)}")
    if errors:
        for e in errors:
            print(f"    - {e['level']} {e['type']}: {e['error']}")

    print(f"\n  Vector store collection : {collection.name}")
    print(f"  Total vectors in store  : {collection.count()}")

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
