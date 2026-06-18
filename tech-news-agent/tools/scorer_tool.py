from models.article import Article


# ── Source credibility registry ───────────────────────────────────
# Score 1-10. Add/tune as needed.
# Sources not in list → default 5.0 (neutral)
SOURCE_CREDIBILITY: dict[str, float] = {
    # ── Your active sources ──────────────────────────────────────

    # Tier 1 — deep technical / research-grade (9-10)
    "huggingface.co":           9.5,   # primary ML/LLM research source
    "feed.infoq.com":           9.5,   # architect-grade, curated AI/ML/data
    "infoq.com":                9.5,
    "blog.bytebytego.com":      9.0,   # system design, senior architect gold

    # Tier 2 — strong AI/tech signal (7-8)
    "the-decoder.com":          8.0,   # focused AI/LLM coverage
    "kdnuggets.com":            7.5,   # ML/data science, practitioner level
    "venturebeat.com":          7.0,   # AI industry + enterprise tech
    "marktechpost.com":         6.5,   # AI research summaries

    # Tier 3 — broad tech news (5-6)
    "techcrunch.com":           5.5,   # wide coverage, filter needed

    # ── Reserve — add more sources later ────────────────────────
    "martinfowler.com":         10.0,
    "highscalability.com":      9.5,
    "thenewstack.io":           8.5,
    "kubernetes.io":            8.5,
    "cncf.io":                  8.5,
    "netflixtechblog.com":      8.0,
    "openai.com":               8.0,
    "anthropic.com":            8.0,
    "aws.amazon.com":           8.0,
    "engineering.linkedin.com": 8.0,
    "dev.to":                   6.0,
    "medium.com":               5.5,
    "substack.com":             5.5,
    "reddit.com":               4.0,
}

# ── Scoring weights (must sum to 1.0) ────────────────────────────
WEIGHT_RELEVANCE   = 0.50   # LLM-assigned topic relevance
WEIGHT_RECENCY     = 0.30   # how fresh the article is
WEIGHT_CREDIBILITY = 0.20   # source credibility


# ─────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────

def compute_final_score(article: Article) -> float:
    """
    Weighted final score (1-10):
        final = (relevance * 0.5) + (recency * 0.3) + (credibility * 0.2)
    """
    credibility = get_source_credibility(article.source)

    final = (
        article.relevance_score  * WEIGHT_RELEVANCE   +
        article.recency_score    * WEIGHT_RECENCY      +
        credibility              * WEIGHT_CREDIBILITY
    )

    return round(min(max(final, 1.0), 10.0), 2)  # clamp 1-10


def get_source_credibility(source: str) -> float:
    """
    Lookup credibility score for a domain.
    Strips www. prefix. Falls back to 5.0 if unknown.
    """
    domain = source.lower().replace("www.", "").strip()

    # exact match
    if domain in SOURCE_CREDIBILITY:
        return SOURCE_CREDIBILITY[domain]

    # partial match — handles subdomains e.g. "blog.cloudflare.com"
    for known_domain, score in SOURCE_CREDIBILITY.items():
        if known_domain in domain or domain in known_domain:
            return score

    return 5.0  # unknown source → neutral


def score_articles(articles: list[Article]) -> list[Article]:
    """
    Attach final_score to all articles.
    Returns articles sorted by final_score descending.
    """
    for article in articles:
        article.final_score = compute_final_score(article)

    return sorted(articles, key=lambda a: a.final_score, reverse=True)


def explain_score(article: Article) -> dict:
    """
    Debug helper — shows score breakdown per article.
    Used by output_node for verbose mode.
    """
    credibility = get_source_credibility(article.source)
    return {
        "title":            article.title[:60],
        "relevance":        f"{article.relevance_score:.1f} × {WEIGHT_RELEVANCE}",
        "recency":          f"{article.recency_score:.1f} × {WEIGHT_RECENCY}",
        "credibility":      f"{credibility:.1f} × {WEIGHT_CREDIBILITY}",
        "final_score":      article.final_score,
    }