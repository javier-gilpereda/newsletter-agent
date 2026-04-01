import logging
from collections import defaultdict

from agent.models import ScoredArticle, SelectedArticles

logger = logging.getLogger(__name__)


def select(
    scored: list[ScoredArticle],
    deep_dive_count: int = 3,
    summary_count: int = 10,
    quick_link_count: int = 8,
    max_per_topic: int = 2,
) -> SelectedArticles:
    """
    Select articles across three tiers with topic diversity.

    - Top N by score → deep dives (no diversity constraint; these are the best)
    - Next M → summaries with max_per_topic diversity cap
    - Remainder → quick links (title + one-liner only)
    """
    if not scored:
        return SelectedArticles(deep_dives=[], summaries=[], quick_links=[])

    deep_dives = scored[:deep_dive_count]
    remaining = scored[deep_dive_count:]

    summaries: list[ScoredArticle] = []
    topic_counts: dict[str, int] = defaultdict(int)
    summary_set: set[str] = set()

    for article in remaining:
        if len(summaries) >= summary_count:
            break
        primary_topic = article.topic_tags[0] if article.topic_tags else "general"
        if topic_counts[primary_topic] < max_per_topic:
            summaries.append(article)
            summary_set.add(article.raw.url_hash)
            topic_counts[primary_topic] += 1

    # Quick links: next articles after summaries, score > 0.2, no diversity cap
    quick_links: list[ScoredArticle] = []
    for article in remaining:
        if article.raw.url_hash in summary_set:
            continue
        if article.relevance_score < 0.2:
            continue
        if len(quick_links) >= quick_link_count:
            break
        quick_links.append(article)

    logger.info(
        "Selected %d deep dives, %d summaries, %d quick links. Topic distribution: %s",
        len(deep_dives), len(summaries), len(quick_links), dict(topic_counts),
    )

    return SelectedArticles(deep_dives=deep_dives, summaries=summaries, quick_links=quick_links)
