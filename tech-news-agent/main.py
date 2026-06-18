from rich.console import Console
from rich.panel import Panel

from agent.graph import compile_graph
from agent.state import AgentState
from config.sources import RSS_FEEDS, SCRAPE_SOURCES
from config.settings import settings

console = Console()


def main():
    console.print(
        Panel(
            "[bold cyan]Tech News Aggregator Agent[/bold cyan]\n"
            "[dim]Senior Tech Architect Edition[/dim]\n\n"
            f"[white]Recency window :[/white] {settings.recency_days} days\n"
            f"[white]Min score      :[/white] {settings.min_relevance_score}\n"
            f"[white]Max output     :[/white] {settings.max_articles_output} articles\n"
            f"[white]RSS sources    :[/white] {len(RSS_FEEDS)}\n"
            f"[white]Scrape sources :[/white] {len(SCRAPE_SOURCES)}\n"
            f"[white]LLM model      :[/white] {settings.azure_openai_deployment_name}",
            title="[bold]Starting Agent[/bold]",
            border_style="cyan",
            padding=(1, 2),
        )
    )

    # ── Build initial state ───────────────────────────────────────
    initial_state: AgentState = {
        "sources":           [s["rss"] for s in RSS_FEEDS] + SCRAPE_SOURCES,
        "raw_articles":      [],
        "filtered_articles": [],
        "scored_articles":   [],
        "ranked_articles":   [],
        "errors":            [],
        "run_summary":       {},
    }

    # ── Compile + run graph ───────────────────────────────────────
    app = compile_graph()

    final_state = app.invoke(initial_state)

    # ── Done ──────────────────────────────────────────────────────
    console.print(
        Panel(
            "[bold green]Agent run complete.[/bold green]",
            border_style="green",
            padding=(0, 2),
        )
    )

    return final_state


if __name__ == "__main__":
    main()