from datetime import datetime, timezone, timedelta
from models.article import Article
from config.settings import settings


def is_within_window(article: Article, days: int | None = None) -> bool:
    """
    Returns True if article published within recency window.
    Falls back to settings.recency_days if days not provided.
    Articles with no publish date → kept (can't confirm old, give benefit of doubt).
    """
    window = days or settings.recency_days

    if article.published_at is None:
        return True  # unknown date → don't drop

    cutoff = datetime.now(timezone.utc) - timedelta(days=window)

    # ensure published_at is timezone-aware for comparison
    pub = _ensure_utc(article.published_at)

    return pub >= cutoff


def compute_recency_score(article: Article) -> float:
    """
    Score 1-10 based on how recent the article is.
    
    Scoring:
        today         → 10.0
        1 day ago     → 9.0
        2 days ago    → 8.0
        ...
        7+ days ago   → 1.0
        unknown date  → 5.0 (neutral)
    """
    if article.published_at is None:
        return 5.0

    now = datetime.now(timezone.utc)
    pub = _ensure_utc(article.published_at)
    age_days = (now - pub).total_seconds() / 86400  # convert to days

    if age_days < 0:
        return 10.0  # future date edge case → treat as fresh

    score = max(1.0, 10.0 - age_days)
    return round(score, 2)


def filter_by_date(
    articles: list[Article],
    days: int | None = None
) -> tuple[list[Article], list[Article]]:
    """
    Split articles into kept + dropped by recency window.
    Also attaches recency_score to kept articles.

    Returns:
        kept    — within window
        dropped — too old
    """
    kept: list[Article] = []
    dropped: list[Article] = []

    for article in articles:
        if is_within_window(article, days):
            article.recency_score = compute_recency_score(article)
            kept.append(article)
        else:
            article.rejection_reason = "too_old"
            dropped.append(article)

    return kept, dropped


def _ensure_utc(dt: datetime) -> datetime:
    """Make naive datetimes UTC-aware."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)