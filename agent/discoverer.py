"""
Source discovery: uses NewsAPI to find new RSS feeds for active topics.
Runs monthly (every N newsletter runs, configured in settings.toml).
"""
import os
import logging
import json
from urllib.parse import urlparse

from anthropic import Anthropic
from db import database

logger = logging.getLogger(__name__)
client = Anthropic()

EVAL_PROMPT = """\
You are evaluating whether a news domain is a quality source for a newsletter.
Return JSON: {"approved": true/false, "name": "Publication Name", "reason": "one sentence"}

Approve if: reputable outlet, original reporting, not a content farm, not a duplicate of common sources.
Reject if: clickbait, aggregator-only, low-quality SEO blog, or already covered by major outlets in the list.
"""

# Common RSS feed path patterns to try for a discovered domain
_RSS_PATHS = ["/feed", "/rss", "/feed/rss", "/rss.xml", "/feed.xml", "/atom.xml"]


def _get_feed_url(domain: str) -> str | None:
    """Try common RSS paths for a domain."""
    import requests
    import feedparser
    for path in _RSS_PATHS:
        url = f"https://{domain}{path}"
        try:
            resp = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                feed = feedparser.parse(resp.content)
                if feed.entries:
                    return url
        except Exception:
            pass
    return None


def discover(topics: list[str], max_new_sources: int = 5):
    """Discover new sources via NewsAPI and validate with Claude."""
    api_key = os.environ.get("NEWSAPI_KEY")
    if not api_key:
        logger.info("NEWSAPI_KEY not set, skipping source discovery")
        return

    try:
        from newsapi import NewsApiClient  # type: ignore
    except ImportError:
        logger.warning("newsapi-python not installed, skipping discovery")
        return

    existing_sources = {s["url"] for s in database.list_all_sources()}
    existing_domains = {urlparse(u).netloc for u in existing_sources}

    newsapi = NewsApiClient(api_key=api_key)
    candidate_domains: dict[str, int] = {}  # domain → frequency

    for topic in topics[:5]:  # limit API calls
        try:
            results = newsapi.get_everything(q=topic, language="en", page_size=20, sort_by="relevancy")
            for article in results.get("articles", []):
                domain = urlparse(article.get("url", "")).netloc
                if domain and domain not in existing_domains:
                    candidate_domains[domain] = candidate_domains.get(domain, 0) + 1
        except Exception as e:
            logger.warning("NewsAPI query failed for topic '%s': %s", topic, e)

    # Sort by frequency — domains appearing across multiple topics are better candidates
    top_candidates = sorted(candidate_domains.items(), key=lambda x: x[1], reverse=True)[:10]
    if not top_candidates:
        logger.info("No new source candidates found")
        return

    existing_names = [s["name"] for s in database.list_all_sources()][:10]
    added = 0

    for domain, freq in top_candidates:
        if added >= max_new_sources:
            break

        prompt = f"""Domain: {domain}
Appears in {freq} topic result(s) across: {', '.join(topics[:5])}
Existing sources already include: {', '.join(existing_names)}

Evaluate this domain as a newsletter source."""

        try:
            response = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=200,
                system=EVAL_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            if raw.startswith("```"):
                raw = "\n".join(raw.split("\n")[1:-1])
            result = json.loads(raw)

            if not result.get("approved"):
                logger.info("Rejected source candidate: %s (%s)", domain, result.get("reason"))
                continue

            feed_url = _get_feed_url(domain)
            if not feed_url:
                logger.info("No RSS feed found for approved candidate: %s", domain)
                continue

            name = result.get("name", domain)
            database.add_source(feed_url, name, quality_score=0.4, auto_discovered=True)
            logger.info("Discovered new source: %s (%s)", name, feed_url)
            added += 1

        except Exception as e:
            logger.warning("Source evaluation failed for %s: %s", domain, e)

    logger.info("Source discovery complete: %d new sources added", added)
