import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from dateutil import parser as dateparser
from urllib.parse import urlparse, urljoin
from tenacity import retry, stop_after_attempt, wait_exponential

from models.article import Article
from config.settings import settings


# ── Headers to mimic real browser — avoid 403s ───────────────────
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; TechNewsAgent/1.0; "
        "+https://github.com/your-org/tech-news-agent)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# ── Article link patterns to SKIP ────────────────────────────────
_SKIP_URL_PATTERNS = [
    "/tag/", "/tags/", "/category/", "/author/",
    "/page/", "/search/", "/about", "/contact",
    "/advertise", "/subscribe", "/newsletter",
    "twitter.com", "linkedin.com", "facebook.com",
    ".pdf", ".png", ".jpg", ".jpeg",
]


# ─────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────

def scrape_articles_from_source(url: str) -> tuple[list[Article], str, str | None]:
    """
    Main entry point — scrape article links from a homepage/blog index.

    Strategy:
        1. Fetch homepage HTML
        2. Extract all article links
        3. For each link — extract title, date, summary
        4. Return Article objects

    Returns:
        articles  — list of Article objects
        method    — "scrape" always
        error     — error string if failed, else None
    """
    try:
        html, final_url = _fetch_html(url)
        if not html:
            return [], "scrape", f"Failed to fetch HTML: {url}"

        links = _extract_article_links(html, base_url=final_url)

        if not links:
            return [], "scrape", f"No article links found on: {url}"

        articles: list[Article] = []
        source_domain = _domain(url)

        for link_url, link_title in links[:30]:  # cap at 30 links per source
            article = _extract_article(link_url, link_title, source_domain)
            if article:
                articles.append(article)

        return articles, "scrape", None

    except Exception as e:
        return [], "scrape", f"Scrape error [{url}]: {str(e)}"


# ─────────────────────────────────────────────────────────────────
# LINK EXTRACTION
# ─────────────────────────────────────────────────────────────────

def _extract_article_links(html: str, base_url: str) -> list[tuple[str, str]]:
    """
    Extract (url, title) pairs from homepage HTML.

    Targets common blog/news patterns:
        <article> tags
        <h1-3> inside <a>
        Common CSS classes: post-title, entry-title, article-title
    """
    soup = BeautifulSoup(html, "lxml")
    seen: set[str] = set()
    links: list[tuple[str, str]] = []

    # ── Strategy 1: <article> tags with <a> ──
    for article_tag in soup.find_all("article"):
        for a in article_tag.find_all("a", href=True):
            title = a.get_text(strip=True)
            href = _resolve_url(a["href"], base_url)
            if _is_valid_article_link(href, title, seen):
                seen.add(href)
                links.append((href, title))

    # ── Strategy 2: heading tags with <a> ──
    if len(links) < 5:
        for tag in soup.find_all(["h1", "h2", "h3"]):
            a = tag.find("a", href=True)
            if a:
                title = a.get_text(strip=True) or tag.get_text(strip=True)
                href = _resolve_url(a["href"], base_url)
                if _is_valid_article_link(href, title, seen):
                    seen.add(href)
                    links.append((href, title))

    # ── Strategy 3: common title CSS classes ──
    if len(links) < 5:
        title_classes = [
            "post-title", "entry-title", "article-title",
            "card-title", "story-title", "blog-title"
        ]
        for cls in title_classes:
            for tag in soup.find_all(class_=cls):
                a = tag.find("a", href=True) or tag
                href = _resolve_url(a.get("href", ""), base_url)
                title = tag.get_text(strip=True)
                if _is_valid_article_link(href, title, seen):
                    seen.add(href)
                    links.append((href, title))

    return links


def _is_valid_article_link(url: str, title: str, seen: set) -> bool:
    """Filter out nav links, tag pages, social links etc."""
    if not url or not title:
        return False
    if url in seen:
        return False
    if len(title) < 10:  # too short to be an article title
        return False
    for pattern in _SKIP_URL_PATTERNS:
        if pattern in url.lower():
            return False
    # must be same domain or subdomain
    return True


# ─────────────────────────────────────────────────────────────────
# ARTICLE EXTRACTION
# ─────────────────────────────────────────────────────────────────

def _extract_article(url: str, fallback_title: str, source: str) -> Article | None:
    """
    Fetch individual article page, extract:
        - title (from <h1> or <title>)
        - published date (meta tags, time elements)
        - summary (first 500 chars of main content)
    """
    try:
        html, _ = _fetch_html(url)
        if not html:
            # still create article with what we have from link
            return Article(
                title=fallback_title,
                url=url,
                source=source,
                fetch_method="scrape",
            )

        soup = BeautifulSoup(html, "lxml")

        title       = _extract_title(soup, fallback_title)
        published   = _extract_date(soup)
        summary     = _extract_summary(soup)

        return Article(
            title=title,
            url=url,
            source=source,
            published_at=published,
            summary=summary,
            content_snippet=summary[:500],
            fetch_method="scrape",
        )

    except Exception:
        # don't crash pipeline — return minimal article
        return Article(
            title=fallback_title,
            url=url,
            source=source,
            fetch_method="scrape",
        )


def _extract_title(soup: BeautifulSoup, fallback: str) -> str:
    """h1 first, then og:title, then <title> tag, then fallback."""
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)

    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return og["content"].strip()

    title_tag = soup.find("title")
    if title_tag:
        return title_tag.get_text(strip=True)

    return fallback


def _extract_date(soup: BeautifulSoup) -> datetime | None:
    """
    Try in order:
        1. <time datetime="..."> element
        2. meta published_time
        3. JSON-LD datePublished
    """
    # Strategy 1 — <time> element
    time_tag = soup.find("time", attrs={"datetime": True})
    if time_tag:
        try:
            return dateparser.parse(time_tag["datetime"]).astimezone(timezone.utc)
        except Exception:
            pass

    # Strategy 2 — Open Graph / meta tags
    for prop in ("article:published_time", "og:published_time", "datePublished"):
        meta = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        if meta and meta.get("content"):
            try:
                return dateparser.parse(meta["content"]).astimezone(timezone.utc)
            except Exception:
                pass

    # Strategy 3 — JSON-LD
    import json, re
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            date_str = data.get("datePublished") or data.get("dateCreated")
            if date_str:
                return dateparser.parse(date_str).astimezone(timezone.utc)
        except Exception:
            pass

    return None


def _extract_summary(soup: BeautifulSoup) -> str:
    """
    Extract main content text.
    Priority: <article> → meta description → first 3 <p> tags
    """
    # Priority 1 — <article> tag
    article_tag = soup.find("article")
    if article_tag:
        text = article_tag.get_text(separator=" ", strip=True)
        return text[:1000]

    # Priority 2 — meta description
    meta_desc = (
        soup.find("meta", attrs={"name": "description"}) or
        soup.find("meta", property="og:description")
    )
    if meta_desc and meta_desc.get("content"):
        return meta_desc["content"].strip()

    # Priority 3 — first 3 meaningful <p> tags
    paragraphs = []
    for p in soup.find_all("p"):
        text = p.get_text(strip=True)
        if len(text) > 50:  # skip nav/footer noise
            paragraphs.append(text)
        if len(paragraphs) >= 3:
            break

    return " ".join(paragraphs)[:1000]


# ─────────────────────────────────────────────────────────────────
# HTTP HELPER
# ─────────────────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=4))
def _fetch_html(url: str) -> tuple[str, str]:
    """
    Fetch URL, return (html_text, final_url).
    final_url captures redirects.
    """
    with httpx.Client(
        timeout=settings.request_timeout,
        follow_redirects=True,
        headers=_HEADERS,
    ) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text, str(resp.url)


# ─────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────

def _resolve_url(href: str, base_url: str) -> str:
    """Turn relative URLs into absolute."""
    if href.startswith("http"):
        return href
    return urljoin(base_url, href)


def _domain(url: str) -> str:
    """https://thenewstack.io/blog → thenewstack.io"""
    return urlparse(url).netloc.replace("www.", "")