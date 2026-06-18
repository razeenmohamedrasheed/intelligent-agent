from rich.console import Console

from agent.state import AgentState
from tools.dedup_tool import deduplicate

console = Console()


def dedup_node(state: AgentState) -> AgentState:
    """
    Node 3 — Dedup

    Removes exact + near-duplicate articles.
    Uses SHA256(url+title) + normalized title matching.

    Updates state:
        filtered_articles → deduplicated list
        run_summary       → dedup stats
    """
    articles = state.get("filtered_articles", [])

    console.rule("[bold cyan]DEDUP NODE[/bold cyan]")
    console.print(f"\n[cyan]→ Deduplicating {len(articles)} articles...[/cyan]")

    unique, dropped = deduplicate(articles)

    run_summary = dict(state.get("run_summary", {}))
    run_summary["after_dedup"]    = len(unique)
    run_summary["dropped_dedup"]  = len(dropped)

    if dropped:
        console.print(f"  [yellow]~[/yellow] Duplicates found:")
        for d in dropped[:5]:   # show max 5
            console.print(f"      • {d.title[:70]}")
        if len(dropped) > 5:
            console.print(f"      ... and {len(dropped) - 5} more")

    console.print(
        f"  [green]✓[/green] Unique  : [bold]{len(unique)}[/bold]\n"
        f"  [red]✗[/red] Dropped : [bold]{len(dropped)}[/bold] (duplicates)"
    )

    return {
        **state,
        "filtered_articles": unique,
        "run_summary": run_summary,
    }