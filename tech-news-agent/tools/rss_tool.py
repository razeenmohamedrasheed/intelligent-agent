import feedparser
import httpx
from datetime import datetime, timezone
from dateutil import parser as dateparser
from urllib.parse import urljoin, urlparse
from tenacity import retry, stop_after_attempt, wait_exponential

from models.article import Article
from config.settings import settings


# ── Common RSS/Atom feed path patterns to probe ──────────────────
_FEED_CANDIDATES = [
    "/feed",
    "/feed/",
    "/rss",
    "/rss.xml",
    "/atom.xml",
    "/feed.xml",
    "/blog/feed",
    "/blog/rss",
    "/feeds/posts/default",   # Blogger
    "/index.xml",             # Hugo
]


# ─────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────

def fetch_articles_from_source(url: str) -> tuple[list[Article], str, str | None]:
    """
    Main entry point per source URL.

    1. Try URL directly as feed
    2. Probe common feed paths
    3. Parse HTML <link> tags for feed discovery

    Returns:
        articles    — list of Article objects
        method      — "rss" always (scrape_tool handles fallback)
        error       — error string if failed, else None
    """
    feed_url = _discover_feed_url(url)

    if feed_url is None:
        return [], "rss", f"No RSS feed found for {url}"

    articles, error = _parse_feed(feed_url, source_domain=_domain(url))
    return articles, "rss", error


def is_rss_available(url: str) -> bool:
    """Quick check — used by ingest_node to decide rss vs scrape."""
    return _discover_feed_url(url) is not None


# ─────────────────────────────────────────────────────────────────
# FEED DISCOVERY
# ─────────────────────────────────────────────────────────────────

def _discover_feed_url(url: str) -> str | None:
    """
    Try 3 strategies in order:
        1. URL itself is a valid feed
        2. Probe common feed paths
        3. Parse HTML <link rel="alternate"> tags
    """
    # Strategy 1 — maybe URL is already a feed
    if _is_valid_feed(url):
        return url

    base = _base_url(url)

    # Strategy 2 — probe common paths
    for path in _FEED_CANDIDATES:
        candidate = urljoin(base, path)
        if _is_valid_feed(candidate):
            return candidate

    # Strategy 3 — HTML link tag discovery
    feed_url = _discover_from_html(url)
    if feed_url:
        return feed_url

    return None


def _is_valid_feed(url: str) -> bool:
    """Fetch URL, check if feedparser recognizes it as a feed."""
    try:
        feed = feedparser.parse(url)
        # feedparser sets bozo=True for malformed, version="" for non-feeds
        return bool(feed.version) and len(feed.entries) > 0
    except Exception:
        return False


def _discover_from_html(url: str) -> str | None:
    """
    Fetch homepage HTML, look for:
        <link rel="alternate" type="application/rss+xml" href="...">
        <link rel="alternate" type="application/atom+xml" href="...">
    """
    try:
        resp = _get(url)
        if resp is None:
            return None

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "lxml")

        for link in soup.find_all("link", rel="alternate"):
            link_type = link.get("type", "")
            if "rss" in link_type or "atom" in link_type:
                href = link.get("href", "")
                if href:
                    # handle relative URLs
                    return urljoin(url, href)
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────────────────────────
# FEED PARSING
# ─────────────────────────────────────────────────────────────────

def _parse_feed(feed_url: str, source_domain: str) -> tuple[list[Article], str | None]:
    """Parse feed entries into Article objects."""
    try:
        feed = feedparser.parse(feed_url)

        if not feed.entries:
            return [], f"Feed empty or unreadable: {feed_url}"

        articles: list[Article] = []

        for entry in feed.entries:
            article = _entry_to_article(entry, source_domain)
            if article:
                articles.append(article)

        return articles, None

    except Exception as e:
        return [], f"Feed parse error [{feed_url}]: {str(e)}"


def _entry_to_article(entry: feedparser.FeedParserDict, source: str) -> Article | None:
    """Map a feedparser entry → Article model."""
    try:
        title = entry.get("title", "").strip()
        url   = entry.get("link", "").strip()

        if not title or not url:
            return None  # skip malformed entries

        # ── Summary / content ──
        summary = ""
        if entry.get("summary"):
            summary = _strip_html(entry.summary)
        elif entry.get("content"):
            summary = _strip_html(entry.content[0].value)

        content_snippet = summary[:500]

        # ── Published date ──
        published_at = _parse_date(entry)

        return Article(
            title=title,
            url=url,
            source=source,
            published_at=published_at,
            summary=summary[:1000],
            content_snippet=content_snippet,
            fetch_method="rss",
        )

    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=4))
def _get(url: str) -> httpx.Response | None:
    """HTTP GET with retries."""
    with httpx.Client(timeout=settings.request_timeout, follow_redirects=True) as client:
        resp = client.get(url, headers={"User-Agent": "TechNewsAgent/1.0"})
        resp.raise_for_status()
        return resp


def _parse_date(entry: feedparser.FeedParserDict) -> datetime | None:
    """Try multiple feedparser date fields, return UTC datetime."""
    for field in ("published_parsed", "updated_parsed", "created_parsed"):
        val = entry.get(field)
        if val:
            try:
                import time
                ts = time.mktime(val)
                return datetime.fromtimestamp(ts, tz=timezone.utc)
            except Exception:
                pass

    # fallback — try raw string fields
    for field in ("published", "updated"):
        val = entry.get(field)
        if val:
            try:
                return dateparser.parse(val).astimezone(timezone.utc)
            except Exception:
                pass

    return None


def _strip_html(html: str) -> str:
    """Remove HTML tags from summary/content."""
    try:
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "lxml").get_text(separator=" ").strip()
    except Exception:
        import re
        return re.sub(r"<[^>]+>", "", html).strip()


def _base_url(url: str) -> str:
    """Extract scheme + netloc: https://thenewstack.io/blog/post → https://thenewstack.io"""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _domain(url: str) -> str:
    """Extract domain: https://thenewstack.io/blog → thenewstack.io"""
    return urlparse(url).netloc.replace("www.", "")