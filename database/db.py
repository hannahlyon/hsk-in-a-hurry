"""SQLite (local) / Postgres (Heroku) init, connection, and CRUD helpers."""
import os
import sqlite3
from pathlib import Path
from typing import Any, List, Optional

from config.settings import DB_PATH

DATABASE_URL = os.getenv("DATABASE_URL", "")
_PG = bool(DATABASE_URL)
PH = "%s" if _PG else "?"  # SQL placeholder

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def get_connection():
    if _PG:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        # Heroku sets postgres:// but psycopg2 prefers postgresql://
        url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        conn = psycopg2.connect(url)
        conn.cursor_factory = RealDictCursor
        return conn
    else:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


def init_db() -> None:
    """Apply schema — idempotent due to IF NOT EXISTS."""
    if _PG:
        schema = (_SCHEMA_PATH.parent / "schema_pg.sql").read_text()
        with get_connection() as conn:
            with conn.cursor() as cur:
                for statement in schema.split(";"):
                    stmt = statement.strip()
                    if stmt:
                        cur.execute(stmt)
            conn.commit()
    else:
        schema = _SCHEMA_PATH.read_text()
        with get_connection() as conn:
            conn.executescript(schema)


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _execute(conn, sql: str, params=()) -> None:
    if _PG:
        with conn.cursor() as cur:
            cur.execute(sql, params)
    else:
        conn.execute(sql, params)


def _fetchone(conn, sql: str, params=()):
    if _PG:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()
    else:
        return conn.execute(sql, params).fetchone()


def _fetchall(conn, sql: str, params=()):
    if _PG:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    else:
        return conn.execute(sql, params).fetchall()


def _executemany(conn, sql: str, params_list) -> None:
    if _PG:
        import psycopg2.extras
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, sql, params_list)
    else:
        conn.executemany(sql, params_list)


def _insert(conn, sql: str, params) -> int:
    """Execute INSERT, return new row id."""
    if _PG:
        with conn.cursor() as cur:
            cur.execute(sql + " RETURNING id", params)
            return cur.fetchone()["id"]
    else:
        cur = conn.execute(sql, params)
        return cur.lastrowid


# ---------------------------------------------------------------------------
# Newsletter CRUD
# ---------------------------------------------------------------------------

def insert_newsletter(name: str, language: str, exam: str,
                      substack_url: Optional[str] = None,
                      substack_pub_id: Optional[str] = None) -> int:
    with get_connection() as conn:
        return _insert(conn,
            f"INSERT INTO newsletters (name, language, exam, substack_url, substack_pub_id) "
            f"VALUES ({PH}, {PH}, {PH}, {PH}, {PH})",
            (name, language, exam, substack_url, substack_pub_id),
        )


def get_newsletters() -> List[dict]:
    with get_connection() as conn:
        rows = _fetchall(conn, "SELECT * FROM newsletters ORDER BY created_at DESC")
        return [dict(r) for r in rows]


def get_newsletter(newsletter_id: int) -> Optional[dict]:
    with get_connection() as conn:
        row = _fetchone(conn, f"SELECT * FROM newsletters WHERE id = {PH}", (newsletter_id,))
        return dict(row) if row else None


def update_newsletter(newsletter_id: int, **kwargs: Any) -> None:
    cols = ", ".join(f"{k} = {PH}" for k in kwargs)
    vals = list(kwargs.values()) + [newsletter_id]
    with get_connection() as conn:
        _execute(conn, f"UPDATE newsletters SET {cols} WHERE id = {PH}", vals)


# ---------------------------------------------------------------------------
# Scrape sessions
# ---------------------------------------------------------------------------

def insert_scrape_session(newsletter_id: int, language: str, exam: str,
                           level: str, content_type: str, source_url: str) -> int:
    with get_connection() as conn:
        return _insert(conn,
            f"INSERT INTO scrape_sessions "
            f"(newsletter_id, language, exam, level, content_type, source_url) "
            f"VALUES ({PH}, {PH}, {PH}, {PH}, {PH}, {PH})",
            (newsletter_id, language, exam, level, content_type, source_url),
        )


def update_scrape_session(session_id: int, **kwargs: Any) -> None:
    cols = ", ".join(f"{k} = {PH}" for k in kwargs)
    vals = list(kwargs.values()) + [session_id]
    with get_connection() as conn:
        _execute(conn, f"UPDATE scrape_sessions SET {cols} WHERE id = {PH}", vals)


# ---------------------------------------------------------------------------
# Scraped chunks
# ---------------------------------------------------------------------------

def insert_chunks(chunks: List[dict]) -> List[int]:
    """Bulk-insert scraped chunks; returns list of inserted IDs."""
    if _PG:
        sql = (
            "INSERT INTO scraped_chunks "
            "(session_id, language, exam, level, content_type, source_url, "
            "chunk_text, chunk_index, chroma_doc_id) "
            "VALUES (%(session_id)s, %(language)s, %(exam)s, %(level)s, %(content_type)s, "
            "%(source_url)s, %(chunk_text)s, %(chunk_index)s, %(chroma_doc_id)s)"
        )
    else:
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
            ids.append(_insert(conn, sql, chunk))
    return ids


def mark_chunks_embedded(chunk_ids: List[int]) -> None:
    with get_connection() as conn:
        _executemany(
            conn,
            f"UPDATE scraped_chunks SET embedded = 1 WHERE id = {PH}",
            [(cid,) for cid in chunk_ids],
        )


def get_unembedded_chunks(language: str, exam: str, level: str) -> List[dict]:
    with get_connection() as conn:
        rows = _fetchall(conn,
            f"SELECT * FROM scraped_chunks WHERE embedded = 0 "
            f"AND language = {PH} AND exam = {PH} AND level = {PH}",
            (language, exam, level),
        )
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
        return _insert(conn,
            f"INSERT INTO generated_posts "
            f"(newsletter_id, title, content_type, language, exam, level, "
            f"grammar_focus, vocab_focus, content_html, content_raw, retrieval_ids) "
            f"VALUES ({PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH})",
            (newsletter_id, title, content_type, language, exam, level,
             grammar_focus, vocab_focus, content_html, content_raw, retrieval_ids),
        )


def get_generated_posts(newsletter_id: Optional[int] = None) -> List[dict]:
    with get_connection() as conn:
        if newsletter_id:
            rows = _fetchall(conn,
                f"SELECT * FROM generated_posts WHERE newsletter_id = {PH} ORDER BY created_at DESC",
                (newsletter_id,),
            )
        else:
            rows = _fetchall(conn, "SELECT * FROM generated_posts ORDER BY created_at DESC")
        return [dict(r) for r in rows]


def get_generated_post(post_id: int) -> Optional[dict]:
    with get_connection() as conn:
        row = _fetchone(conn,
            f"SELECT * FROM generated_posts WHERE id = {PH}", (post_id,)
        )
        return dict(row) if row else None


def update_generated_post(post_id: int, **kwargs: Any) -> None:
    cols = ", ".join(f"{k} = {PH}" for k in kwargs)
    vals = list(kwargs.values()) + [post_id]
    with get_connection() as conn:
        _execute(conn, f"UPDATE generated_posts SET {cols} WHERE id = {PH}", vals)


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

def upsert_analytics_snapshot(newsletter_id: int, snapshot_date: str,
                               data: dict) -> int:
    with get_connection() as conn:
        _execute(conn,
            f"DELETE FROM analytics_snapshots WHERE newsletter_id = {PH} AND snapshot_date = {PH}",
            (newsletter_id, snapshot_date),
        )
        return _insert(conn,
            f"INSERT INTO analytics_snapshots "
            f"(newsletter_id, snapshot_date, total_subscribers, paid_subscribers, "
            f"free_subscribers, total_views, open_rate_30d, new_subs_period, snapshot_raw) "
            f"VALUES ({PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH})",
            (newsletter_id, snapshot_date,
             data.get("total_subscribers"), data.get("paid_subscribers"),
             data.get("free_subscribers"), data.get("total_views"),
             data.get("open_rate_30d"), data.get("new_subs_period"),
             data.get("snapshot_raw")),
        )


def get_analytics_snapshots(newsletter_id: int, days: int = 30) -> List[dict]:
    if _PG:
        # days is always an int — safe to interpolate directly
        sql = (
            f"SELECT * FROM analytics_snapshots "
            f"WHERE newsletter_id = {PH} "
            f"AND snapshot_date >= CURRENT_DATE - INTERVAL '{days} days' "
            f"ORDER BY snapshot_date ASC"
        )
        params = (newsletter_id,)
    else:
        sql = (
            f"SELECT * FROM analytics_snapshots "
            f"WHERE newsletter_id = {PH} "
            f"AND snapshot_date >= date('now', {PH}) "
            f"ORDER BY snapshot_date ASC"
        )
        params = (newsletter_id, f"-{days} days")
    with get_connection() as conn:
        rows = _fetchall(conn, sql, params)
        return [dict(r) for r in rows]


def upsert_post_analytics(newsletter_id: int, post_id: str, data: dict) -> None:
    with get_connection() as conn:
        _execute(conn,
            f"DELETE FROM post_analytics WHERE newsletter_id = {PH} AND post_id = {PH}",
            (newsletter_id, post_id),
        )
        _execute(conn,
            f"INSERT INTO post_analytics "
            f"(newsletter_id, post_id, post_title, published_at, emails_sent, "
            f"emails_opened, open_rate, total_views, unique_views, clicks) "
            f"VALUES ({PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH})",
            (newsletter_id, post_id, data.get("post_title"), data.get("published_at"),
             data.get("emails_sent"), data.get("emails_opened"), data.get("open_rate"),
             data.get("total_views"), data.get("unique_views"), data.get("clicks")),
        )


def get_post_analytics(newsletter_id: int) -> List[dict]:
    with get_connection() as conn:
        rows = _fetchall(conn,
            f"SELECT * FROM post_analytics WHERE newsletter_id = {PH} ORDER BY published_at DESC",
            (newsletter_id,),
        )
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
        return _insert(conn,
            f"INSERT INTO social_posts "
            f"(generated_post_id, platform, copy_text, hashtags, "
            f"image_prompt, image_path, image_size) "
            f"VALUES ({PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH})",
            (generated_post_id, platform, copy_text, hashtags,
             image_prompt, image_path, image_size),
        )


def get_social_posts(generated_post_id: int) -> List[dict]:
    with get_connection() as conn:
        rows = _fetchall(conn,
            f"SELECT * FROM social_posts WHERE generated_post_id = {PH}",
            (generated_post_id,),
        )
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Website users
# ---------------------------------------------------------------------------

def create_user(name: str, email: str, password_hash: str) -> int:
    with get_connection() as conn:
        return _insert(conn,
            f"INSERT INTO website_users (name, email, password_hash) VALUES ({PH}, {PH}, {PH})",
            (name, email, password_hash),
        )


def get_user_by_email(email: str) -> Optional[dict]:
    with get_connection() as conn:
        row = _fetchone(conn,
            f"SELECT * FROM website_users WHERE email = {PH}", (email,)
        )
        return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[dict]:
    with get_connection() as conn:
        row = _fetchone(conn,
            f"SELECT * FROM website_users WHERE id = {PH}", (user_id,)
        )
        return dict(row) if row else None


def update_user_subscription(email: str, status: str,
                              stripe_customer_id: Optional[str] = None,
                              subscription_id: Optional[str] = None) -> None:
    with get_connection() as conn:
        _execute(conn,
            f"UPDATE website_users SET subscription_status = {PH}, "
            f"stripe_customer_id = COALESCE({PH}, stripe_customer_id), "
            f"subscription_id = COALESCE({PH}, subscription_id) "
            f"WHERE email = {PH}",
            (status, stripe_customer_id, subscription_id, email),
        )
