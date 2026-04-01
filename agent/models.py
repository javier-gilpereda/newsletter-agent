from dataclasses import dataclass, field
from datetime import datetime
from pydantic import BaseModel


# ── Raw pipeline data (dataclasses, lightweight) ────────────────────────────

@dataclass
class RawArticle:
    url: str
    url_hash: str
    title: str
    source_id: int
    source_name: str
    published_at: datetime | None
    snippet: str  # first ~500 chars of description


@dataclass
class ScoredArticle:
    raw: RawArticle
    relevance_score: float
    topic_tags: list[str]
    is_time_sensitive: bool
    importance_note: str


@dataclass
class SelectedArticles:
    deep_dives: list[ScoredArticle]
    summaries: list[ScoredArticle]


# ── Claude structured output models (Pydantic) ──────────────────────────────

class ArticleScore(BaseModel):
    url_hash: str
    relevance_score: float       # 0.0–1.0
    topic_tags: list[str]        # which user topics this matches
    is_time_sensitive: bool
    importance_note: str         # one-line reason (for debugging)


class ArticleScoreList(BaseModel):
    scores: list[ArticleScore]


class DeepDive(BaseModel):
    url_hash: str
    title: str
    body: str          # ~300 words: context + developments + why it matters
    source_name: str
    url: str


class Summary(BaseModel):
    url_hash: str
    title: str
    body: str          # ~80 words
    source_name: str
    url: str


class Newsletter(BaseModel):
    subject_line: str
    intro_paragraph: str
    deep_dives: list[DeepDive]
    summaries: list[Summary]
    outro: str
    estimated_word_count: int
