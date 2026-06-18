from datetime import datetime
from pydantic import BaseModel, Field


class Article(BaseModel):
    # ── Core fields (populated at ingest) ──
    title: str
    url: str
    source: str                         # domain name e.g. "thenewstack.io"
    published_at: datetime | None = None
    summary: str = ""                   # raw excerpt or scraped text
    content_snippet: str = ""          # first ~500 chars of content

    # ── Populated by filter/rank nodes ──
    topic_tags: list[str] = Field(default_factory=list)   # e.g. ["LLM", "Kubernetes"]
    relevance_score: float = 0.0        # 1-10, LLM assigned
    recency_score: float = 0.0          # computed from published_at
    final_score: float = 0.0            # weighted combo

    # ── Guardrail flags ──
    is_duplicate: bool = False
    rejection_reason: str = ""          # why guardrail dropped it

    # ── Internal ──
    content_hash: str = ""              # SHA256(url+title) for dedup
    fetch_method: str = ""              # "rss" or "scrape"