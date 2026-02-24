"""OpenAI text-embedding-3-small batch embedder."""
import hashlib
from typing import List, Optional

from openai import OpenAI

from config.settings import OPENAI_API_KEY, EMBEDDING_MODEL
from utils.logger import get_logger
from utils.helpers import chunk_list

log = get_logger(__name__)


def _get_client() -> OpenAI:
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not set in .env")
    return OpenAI(api_key=OPENAI_API_KEY)


def embed_texts(texts: List[str], batch_size: int = 100) -> List[List[float]]:
    """
    Embed a list of texts using text-embedding-3-small.
    Returns list of embedding vectors in the same order.
    """
    client = _get_client()
    all_embeddings = []
    for batch in chunk_list(texts, batch_size):
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=batch,
        )
        batch_embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embeddings)
        log.debug("Embedded batch of %d texts", len(batch))
    return all_embeddings


def make_chunk_id(source_url: str, chunk_index: int) -> str:
    """Deterministic chunk ID: sha256(url + index)[:16]."""
    raw = f"{source_url}{chunk_index}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def embed_and_upsert(chunks: List[dict], collection,
                     sqlite_ids: Optional[List[int]] = None) -> List[str]:
    """
    Embed chunk texts and upsert into a ChromaDB collection.
    Returns list of chroma doc IDs.

    Each chunk dict must have: chunk_text, source_url, chunk_index,
    language, exam, level, content_type.
    """
    if not chunks:
        return []

    texts = [c["chunk_text"] for c in chunks]
    embeddings = embed_texts(texts)

    doc_ids = []
    documents = []
    metadatas = []
    ids = []

    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        doc_id = make_chunk_id(chunk["source_url"], chunk["chunk_index"])
        doc_ids.append(doc_id)
        documents.append(chunk["chunk_text"])
        ids.append(doc_id)

        meta = {
            "language": chunk.get("language", ""),
            "exam": chunk.get("exam", ""),
            "level": chunk.get("level", ""),
            "content_type": chunk.get("content_type", ""),
            "source_url": chunk.get("source_url", ""),
            "grammar_point": chunk.get("grammar_point") or "",
            "char_count": len(chunk["chunk_text"]),
        }
        if sqlite_ids and i < len(sqlite_ids):
            meta["sqlite_chunk_id"] = str(sqlite_ids[i])

        metadatas.append(meta)

    # Upsert in batches of 100 (ChromaDB recommendation)
    for batch_start in range(0, len(ids), 100):
        collection.upsert(
            ids=ids[batch_start:batch_start + 100],
            documents=documents[batch_start:batch_start + 100],
            embeddings=embeddings[batch_start:batch_start + 100],
            metadatas=metadatas[batch_start:batch_start + 100],
        )
    log.info("Upserted %d chunks into collection '%s'", len(ids), collection.name)
    return doc_ids
