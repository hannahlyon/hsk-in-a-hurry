"""SQLite init, connection, and CRUD helpers."""
import sqlite3
from pathlib import Path
from typing import Any, List, Optional

from config.settings import DB_PATH

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Apply schema.sql — idempotent due to IF NOT EXISTS."""
    schema = _SCHEMA_PATH.read_text()
    with get_connection() as conn:
        conn.executescript(schema)


# ---------------------------------------------------------------------------
# Newsletter CRUD
# ---------------------------------------------------------------------------

def insert_newsletter(name: str, language: str, exam: str,
                      substack_url: Optional[str] = None,
                      substack_pub_id: Optional[str] = None) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO newsletters (name, language, exam, substack_url, substack_pub_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, language, exam, substack_url, substack_pub_id),
        )
        return cur.lastrowid


def get_newsletters() -> List[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM newsletters ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def get_newsletter(newsletter_id: int) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM newsletters WHERE id = ?", (newsletter_id,)).fetchone()
        return dict(row) if row else None


def update_newsletter(newsletter_id: int, **kwargs: Any) -> None:
    cols = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [newsletter_id]
    with get_connection() as conn:
        conn.execute(f"UPDATE newsletters SET {cols} WHERE id = ?", vals)


# ---------------------------------------------------------------------------
# Scrape sessions
# ---------------------------------------------------------------------------

def insert_scrape_session(newsletter_id: int, language: str, exam: str,
                           level: str, content_type: str, source_url: str) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO scrape_sessions "
            "(newsletter_id, language, exam, level, content_type, source_url) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (newsletter_id, language, exam, level, content_type, source_url),
        )
        return cur.lastrowid


def update_scrape_session(session_id: int, **kwargs: Any) -> None:
    cols = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [session_id]
    with get_connection() as conn:
        conn.execute(f"UPDATE scrape_sessions SET {cols} WHERE id = ?", vals)


# ---------------------------------------------------------------------------
# Scraped chunks
# ---------------------------------------------------------------------------

def insert_chunks(chunks: List[dict]) -> List[int]:
    """Bulk-insert scraped chunks; returns list of inserted IDs."""
    sql = (
        "INSERT INTO scraped_chunks "
        "(session_id, language, exam, level, content_type, source_url, "
        "chunk_text, chunk_index, chroma_doc_id) "
        "VALUES (:session_id, :language, :exam, :level, :content_type, :source_url, "
        ":chunk_text, :chunk_index, :chroma_doc_id)"
    )
    ids = []
    with get_connection() as conn:
        for chunk in chunks:
            cur = conn.execute(sql, chunk)
            ids.append(cur.lastrowid)
    return ids


def mark_chunks_embedded(chunk_ids: List[int]) -> None:
    with get_connection() as conn:
        conn.executemany(
            "UPDATE scraped_chunks SET embedded = 1 WHERE id = ?",
            [(cid,) for cid in chunk_ids],
        )


def get_unembedded_chunks(language: str, exam: str, level: str) -> List[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM scraped_chunks WHERE embedded = 0 "
            "AND language = ? AND exam = ? AND level = ?",
            (language, exam, level),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Generated posts
# ---------------------------------------------------------------------------

def insert_generated_post(newsletter_id: int, title: str, content_type: str,
                           language: str, exam: str, level: str,
                           grammar_focus: Optional[str] = None,
                           vocab_focus: Optional[str] = None,
                           content_html: Optional[str] = None,
                           content_raw: Optional[str] = None,
                           retrieval_ids: Optional[str] = None) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO generated_posts "
            "(newsletter_id, title, content_type, language, exam, level, "
            "grammar_focus, vocab_focus, content_html, content_raw, retrieval_ids) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (newsletter_id, title, content_type, language, exam, level,
             grammar_focus, vocab_focus, content_html, content_raw, retrieval_ids),
        )
        return cur.lastrowid


def get_generated_posts(newsletter_id: Optional[int] = None) -> List[dict]:
    with get_connection() as conn:
        if newsletter_id:
            rows = conn.execute(
                "SELECT * FROM generated_posts WHERE newsletter_id = ? ORDER BY created_at DESC",
                (newsletter_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM generated_posts ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]


def get_generated_post(post_id: int) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM generated_posts WHERE id = ?", (post_id,)
        ).fetchone()
        return dict(row) if row else None


def update_generated_post(post_id: int, **kwargs: Any) -> None:
    cols = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [post_id]
    with get_connection() as conn:
        conn.execute(f"UPDATE generated_posts SET {cols} WHERE id = ?", vals)


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

def upsert_analytics_snapshot(newsletter_id: int, snapshot_date: str,
                               data: dict) -> int:
    with get_connection() as conn:
        # Delete existing for same newsletter+date
        conn.execute(
            "DELETE FROM analytics_snapshots WHERE newsletter_id = ? AND snapshot_date = ?",
            (newsletter_id, snapshot_date),
        )
        cur = conn.execute(
            "INSERT INTO analytics_snapshots "
            "(newsletter_id, snapshot_date, total_subscribers, paid_subscribers, "
            "free_subscribers, total_views, open_rate_30d, new_subs_period, snapshot_raw) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (newsletter_id, snapshot_date,
             data.get("total_subscribers"), data.get("paid_subscribers"),
             data.get("free_subscribers"), data.get("total_views"),
             data.get("open_rate_30d"), data.get("new_subs_period"),
             data.get("snapshot_raw")),
        )
        return cur.lastrowid


def get_analytics_snapshots(newsletter_id: int, days: int = 30) -> List[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM analytics_snapshots "
            "WHERE newsletter_id = ? "
            "AND snapshot_date >= date('now', ?) "
            "ORDER BY snapshot_date ASC",
            (newsletter_id, f"-{days} days"),
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_post_analytics(newsletter_id: int, post_id: str, data: dict) -> None:
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM post_analytics WHERE newsletter_id = ? AND post_id = ?",
            (newsletter_id, post_id),
        )
        conn.execute(
            "INSERT INTO post_analytics "
            "(newsletter_id, post_id, post_title, published_at, emails_sent, "
            "emails_opened, open_rate, total_views, unique_views, clicks) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (newsletter_id, post_id, data.get("post_title"), data.get("published_at"),
             data.get("emails_sent"), data.get("emails_opened"), data.get("open_rate"),
             data.get("total_views"), data.get("unique_views"), data.get("clicks")),
        )


def get_post_analytics(newsletter_id: int) -> List[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM post_analytics WHERE newsletter_id = ? ORDER BY published_at DESC",
            (newsletter_id,),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Social posts
# ---------------------------------------------------------------------------

def insert_social_post(generated_post_id: int, platform: str,
                        copy_text: Optional[str] = None,
                        hashtags: Optional[str] = None,
                        image_prompt: Optional[str] = None,
                        image_path: Optional[str] = None,
                        image_size: Optional[str] = None) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO social_posts "
            "(generated_post_id, platform, copy_text, hashtags, "
            "image_prompt, image_path, image_size) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (generated_post_id, platform, copy_text, hashtags,
             image_prompt, image_path, image_size),
        )
        return cur.lastrowid


def get_social_posts(generated_post_id: int) -> List[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM social_posts WHERE generated_post_id = ?",
            (generated_post_id,),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Website users
# ---------------------------------------------------------------------------

def create_user(name: str, email: str, password_hash: str) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO website_users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, password_hash),
        )
        return cur.lastrowid


def get_user_by_email(email: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM website_users WHERE email = ?", (email,)
        ).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM website_users WHERE id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None


def update_user_subscription(email: str, status: str,
                              stripe_customer_id: Optional[str] = None,
                              subscription_id: Optional[str] = None) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE website_users SET subscription_status = ?, "
            "stripe_customer_id = COALESCE(?, stripe_customer_id), "
            "subscription_id = COALESCE(?, subscription_id) "
            "WHERE email = ?",
            (status, stripe_customer_id, subscription_id, email),
        )
