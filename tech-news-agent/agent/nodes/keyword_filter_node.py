import re
from rich.console import Console

from agent.state import AgentState
from models.article import Article

console = Console()


# ─────────────────────────────────────────────────────────────────
# EXCLUSION KEYWORD LISTS
# ─────────────────────────────────────────────────────────────────

# Title must NOT contain these (case-insensitive, word/phrase match)
TITLE_EXCLUDE: list[str] = [
    # ── Crypto / Web3 ──
    "crypto", "cryptocurrency", "bitcoin", "ethereum", "nft", "nfts",
    "web3", "blockchain trading", "defi", "altcoin", "token sale",
    "binance", "coinbase", "solana", "crypto market",

    # ── Career / Roadmap ──
    "roadmap", "how to become", "career path", "career advice",
    "skills to learn", "learning path", "study plan",
    "bootcamp", "self-taught", "get hired", "land a job",
    "resume tips", "interview tips", "salary guide",

    # ── Beginner / Tutorial signals ──
    "for beginners", "beginner's guide", "getting started with",
    "introduction to", "what is ", "explained for",
    "step by step", "step-by-step", "a complete guide",
    "the ultimate guide", "everything you need to know",
    "crash course", "cheat sheet", "101 ",

    # ── Paid / Promo ──
    "sponsored", "paid promotion", "advertisement", "partner content",
    "brought to you by", "in partnership with", "affiliate",
    "discount code", "coupon", "free trial", "sign up now",
    "limited offer", "buy now",

    # ── Clickbait ──
    "you won't believe", "mind blowing", "shocking", "this will change",
    "game changer", "blew my mind", "everyone is talking about",
    "went viral", "broke the internet",

    # ── Social / Roundups ──
    "best tweets", "twitter roundup", "reddit roundup",
    "top posts this week", "weekly digest", "link roundup",
    "this week in ", "last week in ",

    # ── Events / Webinars ──
    "webinar", "register now", "join us for", "free workshop",
    "upcoming event", "conference recap", "meet us at",
    "save the date", "virtual summit",

    # ── Job Posts ──
    "we are hiring", "we're hiring", "job opening", "job posting",
    "now hiring", "open position", "apply now",

    # ── Finance / Non-tech ──
    "stock market", "ipo ", "venture capital", "series a", "series b",
    "funding round", "valuation", "elon musk", "mark zuckerberg",
    "celebrity", "acquisition deal", "merger",

    # ── Listicles / fluff ──
    "top 10 ", "top 5 ", "top 7 ", "best tools for beginners",
    "best laptop", "best mouse", "best keyboard",
    "productivity hacks", "morning routine", "work from home tips",
]

# Source-level exclusions — entire domain blocked
SOURCE_EXCLUDE: list[str] = [
    "coindesk", "cointelegraph", "decrypt.co", "theblock.co",
    "cryptonews", "bitcoinist",
]


# ─────────────────────────────────────────────────────────────────
# NODE
# ─────────────────────────────────────────────────────────────────

def keyword_filter_node(state: AgentState) -> AgentState:
    """
    Node 4 — Keyword Filter (pre-LLM, fast + cheap)

    Drops articles matching exclusion keywords in title.
    Runs BEFORE topic_filter to save LLM tokens.

    Updates state:
        filtered_articles → keyword-clean articles
        run_summary       → keyword filter stats
    """
    articles = state.get("filtered_articles", [])
    errors   = list(state.get("errors", []))

    console.rule("[bold cyan]KEYWORD FILTER NODE[/bold cyan]")
    console.print(f"\n[cyan]→ Keyword filtering {len(articles)} articles...[/cyan]\n")

    passed:   list[Article] = []
    rejected: list[Article] = []

    for article in articles:
        matched_keyword = _matches_exclusion(article)

        if matched_keyword:
            article.rejection_reason = f"keyword_filter: '{matched_keyword}'"
            rejected.append(article)
        else:
            passed.append(article)

    # ── Show sample rejections ────────────────────────────────────
    if rejected:
        console.print(f"  [dim]Sample rejections:[/dim]")
        for a in rejected[:5]:
            console.print(
                f"  [red]✗[/red] {a.title[:65]}  "
                f"[dim]→ {a.rejection_reason}[/dim]"
            )
        if len(rejected) > 5:
            console.print(f"  [dim]  ... and {len(rejected) - 5} more[/dim]")

    run_summary = dict(state.get("run_summary", {}))
    run_summary["after_keyword_filter"]   = len(passed)
    run_summary["dropped_keyword_filter"] = len(rejected)

    console.print(
        f"\n[bold green]Keyword filter complete:[/bold green] "
        f"{len(passed)} passed / [red]{len(rejected)} dropped[/red]"
    )

    return {
        **state,
        "filtered_articles": passed,
        "errors": errors,
        "run_summary": run_summary,
    }


# ─────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────

def _matches_exclusion(article: Article) -> str | None:
    """
    Check title + source against exclusion lists.
    Returns matched keyword/source string, or None if clean.
    """
    title  = article.title.lower()
    source = article.source.lower()

    # source-level block
    for blocked_source in SOURCE_EXCLUDE:
        if blocked_source in source:
            return f"blocked_source:{blocked_source}"

    # title keyword match
    for keyword in TITLE_EXCLUDE:
        # word boundary match for short keywords (e.g. "101 " won't match "10100")
        if keyword.endswith(" "):
            if keyword in title:
                return keyword.strip()
        else:
            # check as substring with word boundaries
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, title, re.IGNORECASE):
                return keyword

    return None