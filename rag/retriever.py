"""ChromaDB query + MMR deduplication."""
from typing import List, Optional, Tuple

from vector_store.chroma_client import get_language_collection
from vector_store.embedder import embed_texts
from config.settings import GRAMMAR_RETRIEVAL_N, VOCAB_RETRIEVAL_N, MMR_SIMILARITY_THRESHOLD
from utils.logger import get_logger

log = get_logger(__name__)


def _mmr_dedup(results: List[dict], threshold: float = MMR_SIMILARITY_THRESHOLD) -> List[dict]:
    """Remove near-duplicate results using cosine similarity threshold."""
    unique = []
    seen_texts: List[str] = []
    for item in results:
        text = item.get("document", "")
        # Simple dedup: check if text shares high overlap with already-seen items
        is_dup = False
        for seen in seen_texts:
            # Jaccard similarity on word sets as proxy for cosine similarity
            set_a = set(text.lower().split())
            set_b = set(seen.lower().split())
            if not set_a or not set_b:
                continue
            jaccard = len(set_a & set_b) / len(set_a | set_b)
            if jaccard > (1 - threshold):
                is_dup = True
                break
        if not is_dup:
            unique.append(item)
            seen_texts.append(text)
    return unique


def query_collection(language: str, exam: str, level: str,
                     query_text: str, content_type: str,
                     n_results: int = 5) -> List[dict]:
    """
    Query ChromaDB collection with language/exam/level filters.
    Returns list of {document, metadata, distance} dicts.
    """
    try:
        collection = get_language_collection(language, exam)
        if collection.count() == 0:
            log.warning("Collection empty for %s %s", language, exam)
            return []

        embeddings = embed_texts([query_text])
        query_embedding = embeddings[0]

        where = {
            "$and": [
                {"language": {"$eq": language}},
                {"exam": {"$eq": exam}},
                {"level": {"$eq": level}},
                {"content_type": {"$eq": content_type}},
            ]
        }

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(n_results, collection.count()),
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        items = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            items.append({"document": doc, "metadata": meta, "distance": dist})

        return _mmr_dedup(items)

    except Exception as exc:
        log.error("query_collection error: %s", exc)
        return []


def retrieve_for_generation(language: str, exam: str, level: str,
                              theme: str) -> Tuple[List[str], List[str]]:
    """
    Run separate grammar + vocab queries for a theme.
    Returns (grammar_chunks, vocab_chunks) as text lists.
    """
    grammar_results = query_collection(
        language, exam, level, theme, "grammar", GRAMMAR_RETRIEVAL_N
    )
    vocab_results = query_collection(
        language, exam, level, theme, "vocabulary", VOCAB_RETRIEVAL_N
    )

    grammar_chunks = [r["document"] for r in grammar_results]
    vocab_chunks = [r["document"] for r in vocab_results]

    log.info("Retrieved %d grammar + %d vocab chunks for theme '%s'",
             len(grammar_chunks), len(vocab_chunks), theme)
    return grammar_chunks, vocab_chunks


def get_retrieval_ids(language: str, exam: str, level: str,
                       theme: str) -> List[str]:
    """Return sqlite_chunk_id strings for provenance tracking."""
    grammar_results = query_collection(
        language, exam, level, theme, "grammar", GRAMMAR_RETRIEVAL_N
    )
    vocab_results = query_collection(
        language, exam, level, theme, "vocabulary", VOCAB_RETRIEVAL_N
    )
    ids = []
    for r in grammar_results + vocab_results:
        sqlite_id = r.get("metadata", {}).get("sqlite_chunk_id")
        if sqlite_id:
            ids.append(sqlite_id)
    return ids
