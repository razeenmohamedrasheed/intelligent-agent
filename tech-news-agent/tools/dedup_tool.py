import hashlib
from models.article import Article


def compute_hash(article: Article) -> str:
    """
    Compute SHA256 hash from URL + normalized title.
    URL alone not enough — same story, different URLs (syndicated content).
    """
    raw = f"{article.url.strip().lower()}|{article.title.strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def deduplicate(articles: list[Article]) -> tuple[list[Article], list[Article]]:
    """
    Remove duplicate articles.
    Returns:
        unique   — articles that passed dedup
        dropped  — articles marked as duplicate
    """
    seen_hashes: set[str] = set()
    seen_titles: set[str] = set()
    unique: list[Article] = []
    dropped: list[Article] = []

    for article in articles:
        # compute + attach hash
        h = compute_hash(article)
        article.content_hash = h

        # normalize title for near-duplicate title check
        title_key = _normalize_title(article.title)

        if h in seen_hashes or title_key in seen_titles:
            article.is_duplicate = True
            article.rejection_reason = "duplicate"
            dropped.append(article)
        else:
            seen_hashes.add(h)
            seen_titles.add(title_key)
            unique.append(article)

    return unique, dropped


def _normalize_title(title: str) -> str:
    """
    Strip punctuation + lowercase + collapse whitespace.
    Catches near-duplicates like:
      'K8s 1.30 Released' vs 'K8s 1.30 Released!'
    """
    import re
    title = title.lower()
    title = re.sub(r"[^\w\s]", "", title)   # remove punctuation
    title = re.sub(r"\s+", " ", title).strip()
    return title