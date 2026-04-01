import json
import logging
import requests
import anthropic

from agent.exceptions import LowCreditsError
from agent.models import ScoredArticle, SelectedArticles, Newsletter

logger = logging.getLogger(__name__)
client = anthropic.Anthropic()

SYSTEM_PROMPT = """\
You are a skilled newsletter writer. Write in a clear, engaging, and conversational tone — informed but never dry.

Format rules:
- Deep dives: ~300 words each. Structure: brief context, what happened/is happening, why it matters.
- Summaries: ~80 words each. One tight, informative paragraph.
- Quick links: exactly one sentence (~20 words). Just the core idea — no fluff.
- Intro: 2–3 sentences welcoming the reader to this week's edition.
- Outro: 2–3 sentences signing off warmly.
- Stay within the estimated_word_count you report — target under 2,300 words total.

Return ONLY valid JSON matching the Newsletter schema. No markdown code fences, no extra text.
"""


def _fetch_article_text(url: str, max_chars: int = 4000) -> str:
    """Fetch and extract readable text from an article URL."""
    try:
        from readability import Document
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        doc = Document(resp.text)
        import re
        text = re.sub(r"<[^>]+>", " ", doc.summary())
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars]
    except Exception as e:
        logger.warning("Could not fetch full text for %s: %s", url, e)
        return ""


def write(selected: SelectedArticles, topics: list[str]) -> Newsletter:
    """Generate the full newsletter using Claude."""

    # Fetch full text for deep dives
    deep_dive_texts = []
    for article in selected.deep_dives:
        full_text = _fetch_article_text(article.raw.url)
        deep_dive_texts.append({
            "url_hash": article.raw.url_hash,
            "title": article.raw.title,
            "source": article.raw.source_name,
            "url": article.raw.url,
            "relevance_note": article.importance_note,
            "full_text": full_text or article.raw.snippet,
        })

    summary_texts = [
        {
            "url_hash": a.raw.url_hash,
            "title": a.raw.title,
            "source": a.raw.source_name,
            "url": a.raw.url,
            "snippet": a.raw.snippet,
        }
        for a in selected.summaries
    ]

    quick_link_texts = [
        {
            "url_hash": a.raw.url_hash,
            "title": a.raw.title,
            "source": a.raw.source_name,
            "url": a.raw.url,
            "snippet": a.raw.snippet[:150],
        }
        for a in selected.quick_links
    ]

    schema = """{
  "subject_line": "string",
  "intro_paragraph": "string",
  "deep_dives": [
    {"url_hash": "string", "title": "string", "body": "string", "source_name": "string", "url": "string"}
  ],
  "summaries": [
    {"url_hash": "string", "title": "string", "body": "string", "source_name": "string", "url": "string"}
  ],
  "quick_links": [
    {"url_hash": "string", "title": "string", "description": "string", "source_name": "string", "url": "string"}
  ],
  "outro": "string",
  "estimated_word_count": 0
}"""

    user_message = f"""User's interest topics: {', '.join(topics)}

=== DEEP DIVES (write ~300 words each) ===
{json.dumps(deep_dive_texts, indent=2)}

=== SUMMARIES (write ~80 words each) ===
{json.dumps(summary_texts, indent=2)}

=== QUICK LINKS (one sentence each, ~20 words) ===
{json.dumps(quick_link_texts, indent=2)}

Write the newsletter now. Return JSON matching this schema:
{schema}
"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=6000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.APIStatusError as e:
        if "credit balance" in str(e).lower():
            raise LowCreditsError() from e
        raise

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = "\n".join(raw.split("\n")[1:-1])

    newsletter = Newsletter.model_validate_json(raw)

    # Trim if over limit with a retry
    if newsletter.estimated_word_count > 2300:
        logger.warning("Newsletter over word limit (%d words), requesting trim", newsletter.estimated_word_count)
        trim_response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=6000,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": raw},
                {"role": "user", "content": "The newsletter is too long. Please shorten the summary section entries to ~60 words each and return the updated JSON."},
            ],
        )
        raw2 = trim_response.content[0].text.strip()
        if raw2.startswith("```"):
            raw2 = "\n".join(raw2.split("\n")[1:-1])
        newsletter = Newsletter.model_validate_json(raw2)

    logger.info("Newsletter generated: %d words, %d deep dives, %d summaries, %d quick links",
                newsletter.estimated_word_count, len(newsletter.deep_dives), len(newsletter.summaries), len(newsletter.quick_links))
    return newsletter
