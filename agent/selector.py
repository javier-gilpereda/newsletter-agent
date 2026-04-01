import logging
from collections import defaultdict

from agent.models import ScoredArticle, SelectedArticles

logger = logging.getLogger(__name__)


def select(
    scored: list[ScoredArticle],
    deep_dive_count: int = 3,
    summary_count: int = 10,
    max_per_topic: int = 2,
) -> SelectedArticles:
    """
    Select deep-dive and summary articles with topic diversity.

    - Top N by score → deep dives (no diversity constraint; these are the best)
    - Remaining → summaries with max_per_topic diversity cap
    """
    if not scored:
        return SelectedArticles(deep_dives=[], summaries=[])

    deep_dives = scored[:deep_dive_count]
    remaining = scored[deep_dive_count:]

    summaries: list[ScoredArticle] = []
    topic_counts: dict[str, int] = defaultdict(int)

    for article in remaining:
        if len(summaries) >= summary_count:
            break

        # Use the primary topic tag (first one), or "general" if untagged
        primary_topic = article.topic_tags[0] if article.topic_tags else "general"

        if topic_counts[primary_topic] < max_per_topic:
            summaries.append(article)
            topic_counts[primary_topic] += 1

    logger.info(
        "Selected %d deep dives, %d summaries. Topic distribution: %s",
        len(deep_dives),
        len(summaries),
        dict(topic_counts),
    )

    return SelectedArticles(deep_dives=deep_dives, summaries=summaries)
