import sqlite3
import os
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "memory.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize():
    """Create tables if they don't exist (idempotent)."""
    conn = get_connection()
    with conn:
        conn.executescript(SCHEMA_PATH.read_text())
    conn.close()


# --- Topics ---

def add_topic(name: str) -> bool:
    """Returns True if added, False if already exists."""
    conn = get_connection()
    try:
        with conn:
            conn.execute(
                "INSERT INTO topics (name) VALUES (?) ON CONFLICT(name) DO UPDATE SET active=1",
                (name.lower().strip(),),
            )
        return True
    finally:
        conn.close()


def remove_topic(name: str) -> bool:
    """Soft-delete: sets active=0. Returns True if found."""
    conn = get_connection()
    try:
        with conn:
            cur = conn.execute(
                "UPDATE topics SET active=0 WHERE name=? AND active=1",
                (name.lower().strip(),),
            )
        return cur.rowcount > 0
    finally:
        conn.close()


def get_active_topics() -> list[str]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT name FROM topics WHERE active=1 ORDER BY name").fetchall()
        return [r["name"] for r in rows]
    finally:
        conn.close()


def list_all_topics() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT id, name, active, added_at FROM topics ORDER BY name").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# --- Sources ---

def add_source(url: str, name: str, quality_score: float = 0.5, auto_discovered: bool = False) -> bool:
    conn = get_connection()
    try:
        with conn:
            conn.execute(
                """INSERT INTO sources (url, name, quality_score, auto_discovered)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(url) DO UPDATE SET active=1""",
                (url.strip(), name.strip(), quality_score, int(auto_discovered)),
            )
        return True
    finally:
        conn.close()


def disable_source(source_id: int) -> bool:
    conn = get_connection()
    try:
        with conn:
            cur = conn.execute("UPDATE sources SET active=0 WHERE id=?", (source_id,))
        return cur.rowcount > 0
    finally:
        conn.close()


def get_active_sources() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, url, name, quality_score, auto_discovered, last_fetched FROM sources WHERE active=1 ORDER BY quality_score DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_all_sources() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, url, name, quality_score, active, auto_discovered, last_fetched, added_at FROM sources ORDER BY quality_score DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_source_quality(source_id: int, signal: float):
    """Exponential moving average: new = 0.9 * old + 0.1 * signal."""
    conn = get_connection()
    try:
        with conn:
            conn.execute(
                "UPDATE sources SET quality_score = 0.9 * quality_score + 0.1 * ?, last_fetched = datetime('now') WHERE id=?",
                (signal, source_id),
            )
    finally:
        conn.close()


def mark_source_fetched(source_id: int):
    conn = get_connection()
    try:
        with conn:
            conn.execute("UPDATE sources SET last_fetched = datetime('now') WHERE id=?", (source_id,))
    finally:
        conn.close()


# --- Articles ---

def get_seen_hashes(hashes: list[str]) -> set[str]:
    """Return which hashes have already been used in a newsletter run."""
    if not hashes:
        return set()
    conn = get_connection()
    try:
        placeholders = ",".join("?" * len(hashes))
        rows = conn.execute(
            f"SELECT url_hash FROM articles WHERE url_hash IN ({placeholders}) AND seen_in_run_id IS NOT NULL",
            hashes,
        ).fetchall()
        return {r["url_hash"] for r in rows}
    finally:
        conn.close()


def upsert_articles(articles: list[dict]):
    """Insert new articles (ignore if url_hash already exists)."""
    conn = get_connection()
    try:
        with conn:
            conn.executemany(
                """INSERT OR IGNORE INTO articles (url_hash, url, title, source_id, published_at)
                   VALUES (:url_hash, :url, :title, :source_id, :published_at)""",
                articles,
            )
    finally:
        conn.close()


def mark_articles_seen(url_hashes: list[str], run_id: int, scores: dict[str, float]):
    conn = get_connection()
    try:
        with conn:
            for h in url_hashes:
                conn.execute(
                    "UPDATE articles SET seen_in_run_id=?, relevance_score=? WHERE url_hash=?",
                    (run_id, scores.get(h), h),
                )
    finally:
        conn.close()


# --- Newsletter runs ---

def create_run(topics_snapshot: str) -> int:
    conn = get_connection()
    try:
        with conn:
            cur = conn.execute(
                "INSERT INTO newsletter_runs (topics_snapshot) VALUES (?)",
                (topics_snapshot,),
            )
        return cur.lastrowid
    finally:
        conn.close()


def finalize_run(run_id: int, article_count: int, content_md: str, content_html: str, delivered: bool, method: str):
    conn = get_connection()
    try:
        with conn:
            conn.execute(
                """UPDATE newsletter_runs
                   SET article_count=?, content_md=?, content_html=?, delivered=?, delivery_method=?
                   WHERE id=?""",
                (article_count, content_md, content_html, int(delivered), method, run_id),
            )
    finally:
        conn.close()


def save_topic_coverage(run_id: int, coverage: dict[str, int]):
    conn = get_connection()
    try:
        with conn:
            conn.executemany(
                "INSERT INTO topic_article_coverage (run_id, topic_name, article_count) VALUES (?, ?, ?)",
                [(run_id, topic, count) for topic, count in coverage.items()],
            )
    finally:
        conn.close()


def get_recent_coverage(n_runs: int = 2) -> list[dict]:
    """Return topic coverage for the last n completed runs."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT r.run_at, c.topic_name, c.article_count
               FROM topic_article_coverage c
               JOIN newsletter_runs r ON r.id = c.run_id
               WHERE r.delivered = 1
               ORDER BY r.run_at DESC
               LIMIT ?""",
            (n_runs * 20,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_last_newsletter() -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM newsletter_runs WHERE delivered=1 ORDER BY run_at DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def count_completed_runs() -> int:
    conn = get_connection()
    try:
        row = conn.execute("SELECT COUNT(*) as n FROM newsletter_runs WHERE delivered=1").fetchone()
        return row["n"]
    finally:
        conn.close()
