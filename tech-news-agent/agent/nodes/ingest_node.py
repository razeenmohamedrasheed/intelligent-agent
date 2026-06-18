import asyncio
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from agent.state import AgentState
from tools.rss_tool import fetch_articles_from_source
from tools.scrape_tool import scrape_articles_from_source
from config.sources import RSS_FEEDS, SCRAPE_SOURCES
from models.article import Article

console = Console()


def ingest_node(state: AgentState) -> AgentState:
    """
    Node 1 — Ingest

    For each source:
        1. Try RSS feed directly (RSS_FEEDS have known URLs — skip discovery)
        2. For SCRAPE_SOURCES — try RSS auto-detect first, scrape fallback
        3. Collect all articles into state["raw_articles"]

    Updates state:
        raw_articles  → all fetched articles
        errors        → per-source errors (non-fatal)
        run_summary   → fetch stats
    """
    all_articles: list[Article] = []
    errors: list[str] = list(state.get("errors", []))

    console.rule("[bold cyan]INGEST NODE[/bold cyan]")

    # ── Phase 1: RSS_FEEDS (direct — no discovery needed) ─────────
    console.print(f"\n[cyan]→ Fetching {len(RSS_FEEDS)} RSS sources...[/cyan]")

    for source in RSS_FEEDS:
        name    = source["name"]
        rss_url = source["rss"]

        try:
            articles, method, error = fetch_articles_from_source(rss_url)

            if error:
                errors.append(f"[{name}] {error}")
                console.print(f"  [red]✗[/red] {name} — {error}")
                continue

            # tag source name (rss_tool uses domain; override with friendly name)
            for a in articles:
                a.source = name

            all_articles.extend(articles)
            console.print(
                f"  [green]✓[/green] {name} — "
                f"[bold]{len(articles)}[/bold] articles via {method}"
            )

        except Exception as e:
            msg = f"[{name}] Unexpected error: {str(e)}"
            errors.append(msg)
            console.print(f"  [red]✗[/red] {name} — {str(e)}")

    # ── Phase 2: SCRAPE_SOURCES (RSS auto-detect → scrape fallback) ─
    if SCRAPE_SOURCES:
        console.print(f"\n[cyan]→ Processing {len(SCRAPE_SOURCES)} scrape sources...[/cyan]")

        for url in SCRAPE_SOURCES:
            name = _url_to_name(url)

            try:
                # try RSS first
                articles, method, error = fetch_articles_from_source(url)

                if error or not articles:
                    # RSS failed → scrape fallback
                    console.print(f"  [yellow]~[/yellow] {name} — RSS failed, trying scrape...")
                    articles, method, error = scrape_articles_from_source(url)

                if error:
                    errors.append(f"[{name}] {error}")
                    console.print(f"  [red]✗[/red] {name} — {error}")
                    continue

                all_articles.extend(articles)
                console.print(
                    f"  [green]✓[/green] {name} — "
                    f"[bold]{len(articles)}[/bold] articles via {method}"
                )

            except Exception as e:
                msg = f"[{name}] Unexpected error: {str(e)}"
                errors.append(msg)
                console.print(f"  [red]✗[/red] {name} — {str(e)}")

    # ── Summary ────────────────────────────────────────────────────
    run_summary = dict(state.get("run_summary", {}))
    run_summary["total_fetched"]  = len(all_articles)
    run_summary["source_errors"]  = len(errors)
    run_summary["sources_tried"]  = len(RSS_FEEDS) + len(SCRAPE_SOURCES)

    console.print(
        f"\n[bold green]Ingest complete:[/bold green] "
        f"{len(all_articles)} articles from "
        f"{run_summary['sources_tried']} sources "
        f"([red]{len(errors)} errors[/red])"
    )

    return {
        **state,
        "raw_articles": all_articles,
        "errors": errors,
        "run_summary": run_summary,
    }


# ─────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────

def _url_to_name(url: str) -> str:
    """https://thenewstack.io → thenewstack.io"""
    from urllib.parse import urlparse
    return urlparse(url).netloc.replace("www.", "")