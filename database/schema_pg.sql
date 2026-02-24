CREATE TABLE IF NOT EXISTS newsletters (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL, language TEXT NOT NULL, exam TEXT NOT NULL,
    substack_url TEXT, substack_pub_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS scrape_sessions (
    id SERIAL PRIMARY KEY,
    newsletter_id INTEGER REFERENCES newsletters(id),
    language TEXT, exam TEXT, level TEXT, content_type TEXT,
    source_url TEXT NOT NULL, scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    chunk_count INTEGER DEFAULT 0, status TEXT DEFAULT 'pending'
);
CREATE TABLE IF NOT EXISTS scraped_chunks (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES scrape_sessions(id),
    language TEXT, exam TEXT, level TEXT, content_type TEXT,
    source_url TEXT NOT NULL, chunk_text TEXT NOT NULL, chunk_index INTEGER,
    chroma_doc_id TEXT, embedded INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS generated_posts (
    id SERIAL PRIMARY KEY,
    newsletter_id INTEGER REFERENCES newsletters(id),
    title TEXT, content_type TEXT, language TEXT, exam TEXT, level TEXT,
    grammar_focus TEXT, vocab_focus TEXT,
    content_html TEXT, content_raw TEXT, retrieval_ids TEXT,
    published INTEGER DEFAULT 0, substack_post_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, published_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS analytics_snapshots (
    id SERIAL PRIMARY KEY,
    newsletter_id INTEGER REFERENCES newsletters(id),
    snapshot_date DATE NOT NULL,
    total_subscribers INTEGER, paid_subscribers INTEGER, free_subscribers INTEGER,
    total_views INTEGER, open_rate_30d REAL, new_subs_period INTEGER,
    snapshot_raw TEXT
);
CREATE TABLE IF NOT EXISTS post_analytics (
    id SERIAL PRIMARY KEY,
    newsletter_id INTEGER REFERENCES newsletters(id),
    post_id TEXT NOT NULL, post_title TEXT, published_at TIMESTAMP,
    emails_sent INTEGER, emails_opened INTEGER, open_rate REAL,
    total_views INTEGER, unique_views INTEGER, clicks INTEGER,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS social_posts (
    id SERIAL PRIMARY KEY,
    generated_post_id INTEGER REFERENCES generated_posts(id),
    platform TEXT NOT NULL, copy_text TEXT, hashtags TEXT,
    image_prompt TEXT, image_path TEXT, image_size TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS vector_store (
    id TEXT NOT NULL,
    collection TEXT NOT NULL,
    document TEXT,
    embedding BYTEA NOT NULL,
    metadata TEXT,
    PRIMARY KEY (collection, id)
);
CREATE INDEX IF NOT EXISTS idx_vector_collection ON vector_store(collection);
CREATE INDEX IF NOT EXISTS idx_chunks_lang ON scraped_chunks(language, exam, level);
CREATE INDEX IF NOT EXISTS idx_posts_nl ON generated_posts(newsletter_id);
CREATE INDEX IF NOT EXISTS idx_analytics ON analytics_snapshots(newsletter_id, snapshot_date);
CREATE TABLE IF NOT EXISTS website_users (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    stripe_customer_id TEXT,
    subscription_status TEXT DEFAULT 'inactive',
    subscription_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_website_users_email ON website_users(email);
