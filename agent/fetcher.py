import hashlib
import re
import logging
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse

import feedparser

from agent.models import RawArticle
from db import database

logger = logging.getLogger(__name__)

# Tracking params to strip from URLs before hashing
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "referrer", "source", "fbclid", "gclid", "mc_cid", "mc_eid",
}


def canonical_url(url: str) -> str:
    """Strip tracking query params and normalize URL for deduplication."""
    parsed = urlparse(url)
    qs = {k: v for k, v in parse_qs(parsed.query).items() if k.lower() not in _TRACKING_PARAMS}
    clean_query = urlencode({k: v[0] for k, v in qs.items()}, doseq=False)
    return urlunparse(parsed._replace(query=clean_query, fragment=""))


def url_hash(url: str) -> str:
    return hashlib.sha256(canonical_url(url).encode()).hexdigest()


def _parse_date(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def fetch_all(lookback_days: int = 8, max_per_source: int = 50, max_total: int = 500) -> list[RawArticle]:
    """Fetch articles from all active sources, within the lookback window."""
    sources = database.get_active_sources()
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    articles: list[RawArticle] = []

    for source in sources:
        if len(articles) >= max_total:
            break
        try:
            feed = feedparser.parse(source["url"])
            count = 0
            for entry in feed.entries:
                if count >= max_per_source:
                    break
                url = entry.get("link", "")
                title = entry.get("title", "").strip()
                if not url or not title:
                    continue

                pub = _parse_date(entry)
                if pub and pub < cutoff:
                    continue

                snippet = entry.get("summary", entry.get("description", ""))
                # Strip HTML tags from snippet
                snippet = re.sub(r"<[^>]+>", " ", snippet).strip()[:500]

                articles.append(RawArticle(
                    url=url,
                    url_hash=url_hash(url),
                    title=title,
                    source_id=source["id"],
                    source_name=source["name"],
                    published_at=pub,
                    snippet=snippet,
                ))
                count += 1

            database.mark_source_fetched(source["id"])
            logger.info("Fetched %d articles from %s", count, source["name"])
        except Exception as e:
            logger.warning("Failed to fetch source %s (%s): %s", source["name"], source["url"], e)

    return articles
