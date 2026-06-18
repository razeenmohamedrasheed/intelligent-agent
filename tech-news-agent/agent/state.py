from typing import TypedDict
from models.article import Article


class AgentState(TypedDict):
    # ── Input ──
    sources: list[str]               # URLs to process

    # ── Pipeline stages ──
    raw_articles: list[Article]      # after ingest_node
    filtered_articles: list[Article] # after date_filter + dedup
    scored_articles: list[Article]   # after topic_filter + guardrail
    ranked_articles: list[Article]   # after rank_node (final output)

    # ── Meta ──
    errors: list[str]                # non-fatal errors (bad sources etc)
    run_summary: dict                # stats: fetched / filtered / ranked counts