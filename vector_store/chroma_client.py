"""SQLite + numpy vector store — drop-in replacement for ChromaDB client.

Replaces ChromaDB to avoid its irreconcilable pydantic dependency conflicts.
Embeddings are stored as binary blobs in the existing SQLite database.
Cosine similarity search is performed with numpy (already a pandas dependency).
"""
import json
import sqlite3
from typing import Any, Dict, List, Optional

import numpy as np

from config.settings import DB_PATH
from database.db import init_db
from utils.logger import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Filter evaluation (mirrors ChromaDB's $and / $eq where-clause syntax)
# ---------------------------------------------------------------------------

def _matches_where(metadata: dict, where: Optional[dict]) -> bool:
    if not where:
        return True
    if "$and" in where:
        return all(_matches_where(metadata, clause) for clause in where["$and"])
    for key, condition in where.items():
        if isinstance(condition, dict):
            if "$eq" in condition and metadata.get(key) != condition["$eq"]:
                return False
        elif metadata.get(key) != condition:
            return False
    return True


# ---------------------------------------------------------------------------
# Collection — mirrors the ChromaDB Collection API used by this project
# ---------------------------------------------------------------------------

class Collection:
    def __init__(self, name: str):
        self.name = name
        # Ensure DB and table exist
        init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn

    def count(self) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM vector_store WHERE collection = ?",
                (self.name,),
            ).fetchone()
            return row[0] if row else 0

    def upsert(self, ids: List[str], documents: List[str],
               embeddings: List[List[float]], metadatas: List[dict]) -> None:
        with self._conn() as conn:
            for doc_id, document, embedding, metadata in zip(
                ids, documents, embeddings, metadatas
            ):
                emb_blob = np.array(embedding, dtype=np.float32).tobytes()
                conn.execute(
                    """INSERT INTO vector_store (id, collection, document, embedding, metadata)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(collection, id) DO UPDATE SET
                         document = excluded.document,
                         embedding = excluded.embedding,
                         metadata = excluded.metadata""",
                    (doc_id, self.name, document, emb_blob, json.dumps(metadata)),
                )
        log.debug("Upserted %d vectors into '%s'", len(ids), self.name)

    def query(self, query_embeddings: List[List[float]], n_results: int,
              where: Optional[dict] = None,
              include: Optional[List[str]] = None) -> dict:
        query_vec = np.array(query_embeddings[0], dtype=np.float32)
        query_norm = np.linalg.norm(query_vec)
        if query_norm > 0:
            query_vec = query_vec / query_norm

        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, document, embedding, metadata FROM vector_store "
                "WHERE collection = ?",
                (self.name,),
            ).fetchall()

        results = []
        for row in rows:
            meta = json.loads(row["metadata"]) if row["metadata"] else {}
            if not _matches_where(meta, where):
                continue
            emb = np.frombuffer(row["embedding"], dtype=np.float32)
            norm = np.linalg.norm(emb)
            if norm > 0:
                emb = emb / norm
            # Cosine distance = 1 - cosine similarity
            distance = float(1.0 - np.dot(query_vec, emb))
            results.append({
                "id": row["id"],
                "document": row["document"],
                "metadata": meta,
                "distance": distance,
            })

        results.sort(key=lambda r: r["distance"])
        results = results[:n_results]

        return {
            "ids": [[r["id"] for r in results]],
            "documents": [[r["document"] for r in results]],
            "metadatas": [[r["metadata"] for r in results]],
            "distances": [[r["distance"] for r in results]],
        }


# ---------------------------------------------------------------------------
# Module-level API (mirrors chroma_client public interface)
# ---------------------------------------------------------------------------

_collections: dict[str, Collection] = {}


def get_collection(name: str) -> Collection:
    if name not in _collections:
        _collections[name] = Collection(name)
    return _collections[name]


def get_language_collection(language: str, exam: str) -> Collection:
    slug = f"{language}_{exam}".lower().replace(" ", "_").replace("/", "_")
    return get_collection(f"lang_{slug}")


def list_collections() -> list[str]:
    from database.db import get_connection
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT collection FROM vector_store"
        ).fetchall()
    return [r[0] for r in rows]


def collection_count(name: str) -> int:
    return get_collection(name).count()
