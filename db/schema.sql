CREATE TABLE IF NOT EXISTS topics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT UNIQUE NOT NULL,
    active      INTEGER NOT NULL DEFAULT 1,
    added_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sources (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url             TEXT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    quality_score   REAL NOT NULL DEFAULT 0.5,
    active          INTEGER NOT NULL DEFAULT 1,
    auto_discovered INTEGER NOT NULL DEFAULT 0,
    last_fetched    TEXT,
    added_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS articles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url_hash        TEXT UNIQUE NOT NULL,
    url             TEXT NOT NULL,
    title           TEXT NOT NULL,
    source_id       INTEGER REFERENCES sources(id),
    published_at    TEXT,
    fetched_at      TEXT NOT NULL DEFAULT (datetime('now')),
    relevance_score REAL,
    seen_in_run_id  INTEGER REFERENCES newsletter_runs(id)
);

CREATE TABLE IF NOT EXISTS newsletter_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at          TEXT NOT NULL DEFAULT (datetime('now')),
    topics_snapshot TEXT NOT NULL,   -- JSON array of active topic names
    article_count   INTEGER NOT NULL DEFAULT 0,
    delivered       INTEGER NOT NULL DEFAULT 0,
    delivery_method TEXT,
    content_md      TEXT,
    content_html    TEXT
);

CREATE TABLE IF NOT EXISTS topic_article_coverage (
    run_id          INTEGER NOT NULL REFERENCES newsletter_runs(id),
    topic_name      TEXT NOT NULL,
    article_count   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, topic_name)
);

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

INSERT OR IGNORE INTO schema_version (version) VALUES (1);

-- Seed a handful of quality RSS sources across common interest areas
INSERT OR IGNORE INTO sources (url, name, quality_score) VALUES
    ('https://feeds.arstechnica.com/arstechnica/index', 'Ars Technica', 0.8),
    ('https://www.wired.com/feed/rss', 'Wired', 0.75),
    ('https://feeds.feedburner.com/TechCrunch', 'TechCrunch', 0.7),
    ('https://hnrss.org/frontpage', 'Hacker News Front Page', 0.8),
    ('https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml', 'NYT Technology', 0.8),
    ('https://feeds.bbci.co.uk/news/technology/rss.xml', 'BBC Technology', 0.75),
    ('https://www.theverge.com/rss/index.xml', 'The Verge', 0.7),
    ('https://www.technologyreview.com/feed/', 'MIT Technology Review', 0.85),
    ('https://www.scientificamerican.com/platform/morgue/collections/rss/sciam/rss1.0.xsl', 'Scientific American', 0.8),
    ('https://feeds.nature.com/nature/rss/current', 'Nature', 0.9),
    ('https://rss.nytimes.com/services/xml/rss/nyt/Science.xml', 'NYT Science', 0.8),
    ('https://feeds.bbci.co.uk/news/science_and_environment/rss.xml', 'BBC Science', 0.75),
    ('https://www.economist.com/rss', 'The Economist', 0.85),
    ('https://feeds.a.dj.com/rss/RSSWorldNews.xml', 'Wall Street Journal World', 0.8),
    ('https://feeds.bbci.co.uk/news/world/rss.xml', 'BBC World News', 0.8);
