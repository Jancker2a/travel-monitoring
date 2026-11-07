"""
storage/schema.py — Database schema and DDL definitions.
"""

SCHEMA_VERSION = 1

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS filters (
    id TEXT PRIMARY KEY,
    country TEXT,
    title TEXT,
    created_at TEXT DEFAULT (datetime('now', 'utc'))
);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filter_id TEXT NOT NULL REFERENCES filters(id),
    scraped_at TEXT NOT NULL,
    offers_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'ok',
    duration_seconds REAL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS offers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER REFERENCES scrape_runs(id),
    filter_id TEXT NOT NULL,
    hotel_name TEXT NOT NULL,
    canonical_hotel_name TEXT,
    price REAL NOT NULL,
    dates TEXT,
    departure_date TEXT,
    return_date TEXT,
    duration TEXT,
    duration_days INTEGER,
    duration_bucket TEXT,
    departure_airport TEXT,
    rating TEXT,
    ta_rating REAL,
    ta_review_count INTEGER,
    ta_source TEXT,
    scraped_at TEXT NOT NULL,
    url TEXT,
    image_url TEXT,
    offer_url TEXT
);

CREATE TABLE IF NOT EXISTS price_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filter_id TEXT NOT NULL,
    hotel_name TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    created_at TEXT NOT NULL,
    old_price REAL,
    new_price REAL,
    diff_percent REAL,
    details_json TEXT
);

-- High-performance lookup indexes
CREATE INDEX IF NOT EXISTS idx_offers_filter_date ON offers(filter_id, scraped_at);
CREATE INDEX IF NOT EXISTS idx_offers_hotel_date ON offers(hotel_name, scraped_at);
CREATE INDEX IF NOT EXISTS idx_offers_canonical_date ON offers(canonical_hotel_name, scraped_at);
CREATE INDEX IF NOT EXISTS idx_offers_filter_price ON offers(filter_id, price);
CREATE INDEX IF NOT EXISTS idx_scrape_runs_filter_date ON scrape_runs(filter_id, scraped_at);
CREATE INDEX IF NOT EXISTS idx_alerts_filter_date ON price_alerts(filter_id, created_at);
"""
