from rich.console import Console

from agent.state import AgentState
from tools.date_tool import filter_by_date
from config.settings import settings

console = Console()


def date_filter_node(state: AgentState) -> AgentState:
    """
    Node 2 — Date Filter

    Drops articles older than recency window (default 7 days).
    Attaches recency_score to kept articles.

    Updates state:
        filtered_articles → articles within window (replaces raw)
        run_summary       → date filter stats
    """
    raw = state.get("raw_articles", [])

    console.rule("[bold cyan]DATE FILTER NODE[/bold cyan]")
    console.print(f"\n[cyan]→ Filtering {len(raw)} articles (window: {settings.recency_days} days)...[/cyan]")

    kept, dropped = filter_by_date(raw, days=settings.recency_days)

    run_summary = dict(state.get("run_summary", {}))
    run_summary["after_date_filter"] = len(kept)
    run_summary["dropped_too_old"]   = len(dropped)

    console.print(
        f"  [green]✓[/green] Kept  : [bold]{len(kept)}[/bold]\n"
        f"  [red]✗[/red] Dropped: [bold]{len(dropped)}[/bold] (too old)"
    )

    return {
        **state,
        "filtered_articles": kept,
        "run_summary": run_summary,
    }