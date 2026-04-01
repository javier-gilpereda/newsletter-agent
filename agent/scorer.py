import json
import logging
import re
from anthropic import Anthropic

from agent.models import RawArticle, ArticleScore, ArticleScoreList, ScoredArticle

logger = logging.getLogger(__name__)
client = Anthropic()

SYSTEM_PROMPT = """\
You are a news relevance analyst. You receive a list of articles and a set of user interest topics.
Your job is to score each article for relevance and importance.

Rules:
- relevance_score: 0.0 = completely off-topic, 1.0 = perfectly on-topic AND highly important
- topic_tags: only include tags from the provided topics list; empty list if none match
- is_time_sensitive: true if this is breaking news or has a near-term deadline/event
- importance_note: one sentence explaining why this article matters (or doesn't)

Return ONLY valid JSON matching the ArticleScoreList schema. No markdown, no explanation.
"""

_MAX_PRE_FILTER = 80  # max articles to send to Claude after keyword filtering


def _keyword_prefilter(articles: list[RawArticle], topics: list[str]) -> list[RawArticle]:
    """
    Cheap keyword filter before Claude scoring.
    Keep articles whose title or snippet contains at least one word from any topic.
    Always keeps the top _MAX_PRE_FILTER matches to cap API costs.
    """
    # Build keyword set: split each topic into individual words (≥4 chars to avoid noise)
    keywords = {w.lower() for topic in topics for w in re.split(r"\W+", topic) if len(w) >= 4}

    def _score(article: RawArticle) -> int:
        text = (article.title + " " + article.snippet).lower()
        return sum(1 for kw in keywords if kw in text)

    scored = [(a, _score(a)) for a in articles]
    # Sort: articles with keyword hits first, then the rest (preserves diversity)
    scored.sort(key=lambda x: x[1], reverse=True)

    filtered = [a for a, s in scored if s > 0]
    remainder = [a for a, s in scored if s == 0]

    # If we have fewer hits than the cap, pad with highest-quality-source remainder
    result = filtered[:_MAX_PRE_FILTER]
    if len(result) < _MAX_PRE_FILTER:
        result += remainder[: _MAX_PRE_FILTER - len(result)]

    logger.info(
        "Pre-filter: %d → %d articles (%d keyword hits, %d padded)",
        len(articles), len(result), len(filtered), max(0, len(result) - len(filtered)),
    )
    return result


def score(
    articles: list[RawArticle],
    topics: list[str],
    recent_coverage: list[dict],
    batch_size: int = 20,
) -> list[ScoredArticle]:
    """Score articles for relevance. Returns only articles with relevance_score > 0.1."""
    if not articles or not topics:
        return []

    # Step 0: cheap keyword pre-filter to cap Claude API costs
    articles = _keyword_prefilter(articles, topics)

    # Summarize recent topic coverage to help Claude avoid repetition
    coverage_summary = ""
    if recent_coverage:
        from collections import defaultdict
        counts: dict[str, int] = defaultdict(int)
        for row in recent_coverage:
            counts[row["topic_name"]] += row["article_count"]
        top = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:5]
        coverage_summary = "Recent newsletter topic coverage (avoid over-weighting these): " + \
            ", ".join(f"{t}({n})" for t, n in top)

    all_scored: list[ScoredArticle] = []

    for i in range(0, len(articles), batch_size):
        batch = articles[i:i + batch_size]
        articles_text = "\n".join(
            f"{j+1}. hash={a.url_hash[:12]} | {a.title} | {a.snippet[:200]}"
            for j, a in enumerate(batch)
        )

        user_message = f"""User interest topics: {', '.join(topics)}

{coverage_summary}

Articles to score:
{articles_text}

Return JSON: {{"scores": [{{"url_hash": "...", "relevance_score": 0.0, "topic_tags": [], "is_time_sensitive": false, "importance_note": "..."}}]}}
"""

        try:
            response = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=8192,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
            raw = response.content[0].text.strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = "\n".join(raw.split("\n")[1:-1])
            result = ArticleScoreList.model_validate_json(raw)
            score_map = {s.url_hash[:12]: s for s in result.scores}

            for article in batch:
                key = article.url_hash[:12]
                sc = score_map.get(key)
                if sc and sc.relevance_score > 0.1:
                    all_scored.append(ScoredArticle(
                        raw=article,
                        relevance_score=sc.relevance_score,
                        topic_tags=sc.topic_tags,
                        is_time_sensitive=sc.is_time_sensitive,
                        importance_note=sc.importance_note,
                    ))

            logger.info("Scored batch %d-%d: %d relevant", i, i + len(batch), len(all_scored))

        except Exception as e:
            logger.error("Scoring batch %d failed: %s", i, e)

    # Sort by relevance descending
    all_scored.sort(key=lambda x: x.relevance_score, reverse=True)
    return all_scored
