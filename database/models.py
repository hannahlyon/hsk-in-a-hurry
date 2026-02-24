"""TypedDict row models for SQLite tables."""
from typing import Optional, TypedDict


class Newsletter(TypedDict):
    id: int
    name: str
    language: str
    exam: str
    substack_url: Optional[str]
    substack_pub_id: Optional[str]
    created_at: str


class ScrapeSession(TypedDict):
    id: int
    newsletter_id: int
    language: str
    exam: str
    level: str
    content_type: str
    source_url: str
    scraped_at: str
    chunk_count: int
    status: str


class ScrapedChunk(TypedDict):
    id: int
    session_id: int
    language: str
    exam: str
    level: str
    content_type: str
    source_url: str
    chunk_text: str
    chunk_index: int
    chroma_doc_id: Optional[str]
    embedded: int
    created_at: str


class GeneratedPost(TypedDict):
    id: int
    newsletter_id: int
    title: str
    content_type: str
    language: str
    exam: str
    level: str
    grammar_focus: Optional[str]
    vocab_focus: Optional[str]
    content_html: Optional[str]
    content_raw: Optional[str]
    retrieval_ids: Optional[str]
    published: int
    substack_post_id: Optional[str]
    created_at: str
    published_at: Optional[str]


class AnalyticsSnapshot(TypedDict):
    id: int
    newsletter_id: int
    snapshot_date: str
    total_subscribers: Optional[int]
    paid_subscribers: Optional[int]
    free_subscribers: Optional[int]
    total_views: Optional[int]
    open_rate_30d: Optional[float]
    new_subs_period: Optional[int]
    snapshot_raw: Optional[str]


class PostAnalytics(TypedDict):
    id: int
    newsletter_id: int
    post_id: str
    post_title: Optional[str]
    published_at: Optional[str]
    emails_sent: Optional[int]
    emails_opened: Optional[int]
    open_rate: Optional[float]
    total_views: Optional[int]
    unique_views: Optional[int]
    clicks: Optional[int]
    fetched_at: str


class SocialPost(TypedDict):
    id: int
    generated_post_id: int
    platform: str
    copy_text: Optional[str]
    hashtags: Optional[str]
    image_prompt: Optional[str]
    image_path: Optional[str]
    image_size: Optional[str]
    created_at: str
