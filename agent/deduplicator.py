import re
import logging

from agent.models import RawArticle
from db import database

logger = logging.getLogger(__name__)


def _title_tokens(title: str) -> set[str]:
    """Lowercase words, strip punctuation, remove stopwords."""
    stopwords = {"the", "a", "an", "in", "on", "at", "to", "of", "and", "or", "is", "are", "was", "for"}
    words = re.findall(r"[a-z0-9]+", title.lower())
    return {w for w in words if w not in stopwords and len(w) > 2}


def _title_similarity(t1: str, t2: str) -> float:
    s1, s2 = _title_tokens(t1), _title_tokens(t2)
    if not s1 or not s2:
        return 0.0
    return len(s1 & s2) / min(len(s1), len(s2))


def deduplicate(articles: list[RawArticle]) -> list[RawArticle]:
    """
    1. Remove articles already seen in a previous newsletter run (DB lookup).
    2. Remove title-duplicate articles within this batch (keep one per story).
    3. Persist new (unseen) article hashes to DB.
    """
    if not articles:
        return []

    hashes = [a.url_hash for a in articles]
    seen_hashes = database.get_seen_hashes(hashes)

    # Step 1: filter already-sent articles
    fresh = [a for a in articles if a.url_hash not in seen_hashes]
    logger.info("Dedup: %d total → %d after removing already-sent", len(articles), len(fresh))

    # Step 2: title-similarity dedup within batch
    # Sort by source quality (higher quality sources win ties) - source order reflects quality sort
    unique: list[RawArticle] = []
    for article in fresh:
        duplicate = False
        for kept in unique:
            if _title_similarity(article.title, kept.title) >= 0.85:
                duplicate = True
                break
        if not duplicate:
            unique.append(article)

    logger.info("Dedup: %d after title-similarity dedup", len(unique))

    # Step 3: persist new articles to DB (without seen_in_run_id — not yet sent)
    database.upsert_articles([
        {
            "url_hash": a.url_hash,
            "url": a.url,
            "title": a.title,
            "source_id": a.source_id,
            "published_at": a.published_at.isoformat() if a.published_at else None,
        }
        for a in unique
    ])

    return unique
