from datetime import timezone
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

from agent.state import AgentState

console = Console()


def output_node(state: AgentState) -> AgentState:
    """
    Node 7 — Output

    Renders ranked articles as rich terminal output:
        1. Run summary panel   (pipeline stats)
        2. Ranked article table (top N)
        3. Error summary       (if any)

    Does not modify state — pure display node.
    """
    articles    = state.get("ranked_articles", [])
    run_summary = state.get("run_summary", {})
    errors      = state.get("errors", [])

    console.print("\n")

    # ── 1. Pipeline summary panel ─────────────────────────────────
    _render_summary_panel(run_summary, len(errors))

    # ── 2. Articles table ─────────────────────────────────────────
    if not articles:
        console.print(
            Panel(
                "[yellow]No articles passed all filters.[/yellow]\n"
                "Try increasing recency window or lowering MIN_RELEVANCE_SCORE.",
                title="[red]No Results[/red]",
                border_style="red",
            )
        )
        return state

    _render_articles_table(articles)

    # ── 3. Errors (collapsed, dim) ────────────────────────────────
    if errors:
        _render_errors(errors)

    return state


# ─────────────────────────────────────────────────────────────────
# RENDERERS
# ─────────────────────────────────────────────────────────────────

def _render_summary_panel(summary: dict, error_count: int) -> None:
    """Pipeline run stats panel."""
    lines = [
        f"[cyan]Sources tried   :[/cyan] {summary.get('sources_tried', '-')}",
        f"[cyan]Total fetched   :[/cyan] {summary.get('total_fetched', '-')}",
        f"[cyan]After date filter:[/cyan] {summary.get('after_date_filter', '-')}  "
        f"[dim](dropped: {summary.get('dropped_too_old', 0)} too old)[/dim]",
        f"[cyan]After dedup     :[/cyan] {summary.get('after_dedup', '-')}  "
        f"[dim](dropped: {summary.get('dropped_dedup', 0)} duplicates)[/dim]",
        f"[cyan]After topic filter:[/cyan] {summary.get('after_topic_filter', '-')}  "
        f"[dim](dropped: {summary.get('dropped_off_topic', 0)} off-topic)[/dim]",
        f"[cyan]After guardrail  :[/cyan] {summary.get('after_guardrail', '-')}  "
        f"[dim](dropped: {summary.get('dropped_guardrail', 0)} low-quality)[/dim]",
        f"[bold green]Final output     :[/bold green] {summary.get('final_output', '-')} articles",
    ]

    if error_count:
        lines.append(f"[red]Source errors    : {error_count}[/red]")

    console.print(
        Panel(
            "\n".join(lines),
            title="[bold cyan]Pipeline Run Summary[/bold cyan]",
            border_style="cyan",
            padding=(1, 2),
        )
    )
    console.print()


def _render_articles_table(articles) -> None:
    """Main ranked articles table."""
    table = Table(
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta",
        border_style="dim",
        padding=(0, 1),
        expand=True,
        title=f"[bold]Top {len(articles)} Articles — Senior Tech Architect Feed[/bold]",
        title_style="bold cyan",
    )

    # ── Columns ──
    table.add_column("#",          style="dim",          width=3,  justify="right")
    table.add_column("Score",      style="bold yellow",  width=6,  justify="center")
    table.add_column("Title",      style="white",        ratio=3,  no_wrap=False)
    table.add_column("Source",     style="cyan",         width=14)
    table.add_column("Date",       style="dim",          width=11)
    table.add_column("Tags",       style="green",        ratio=1,  no_wrap=False)
    table.add_column("Summary",    style="dim white",    ratio=2,  no_wrap=False)

    for i, article in enumerate(articles, 1):
        score_str = _score_badge(article.final_score)
        date_str  = _format_date(article.published_at)
        tags_str  = _format_tags(article.topic_tags)
        summary   = (article.summary or article.content_snippet or "")[:120]

        table.add_row(
            str(i),
            score_str,
            article.title,
            article.source,
            date_str,
            tags_str,
            summary,
        )

    console.print(table)
    console.print()


def _render_errors(errors: list[str]) -> None:
    """Collapsed error list — dim, non-intrusive."""
    console.print(
        Panel(
            "\n".join(f"[dim]• {e}[/dim]" for e in errors),
            title=f"[yellow]Source Errors ({len(errors)})[/yellow]",
            border_style="yellow",
            padding=(0, 1),
        )
    )


# ─────────────────────────────────────────────────────────────────
# FORMATTERS
# ─────────────────────────────────────────────────────────────────

def _score_badge(score: float) -> str:
    """Color-coded score badge."""
    if score >= 8.5:
        return f"[bold green]{score:.1f}[/bold green]"
    elif score >= 7.0:
        return f"[bold yellow]{score:.1f}[/bold yellow]"
    elif score >= 5.5:
        return f"[yellow]{score:.1f}[/yellow]"
    else:
        return f"[dim]{score:.1f}[/dim]"


def _format_date(dt) -> str:
    """Format datetime to readable string."""
    if dt is None:
        return "unknown"
    try:
        return dt.strftime("%b %d, %Y")
    except Exception:
        return "unknown"


def _format_tags(tags: list[str]) -> str:
    """Format topic tags — max 3, comma separated."""
    if not tags:
        return "[dim]—[/dim]"
    return ", ".join(tags[:3])