import json
from rich.console import Console
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from agent.state import AgentState
from models.article import Article
from config.settings import settings

console = Console()

# ── Guardrail rejection categories ───────────────────────────────
REJECTION_CATEGORIES = [
    "beginner_tutorial",      # how-to for juniors, 101 content
    "opinion_fluff",          # hot takes, listicles, vague predictions
    "marketing_content",      # product promotions, sponsored posts
    "paywalled",              # article behind login/paywall
    "duplicate_story",        # same news rehashed from another source
    "low_depth",              # surface-level, no technical substance
]

SYSTEM_PROMPT = """You are a strict quality guardrail for a Senior Tech Architect news feed.

Your job: reject low-quality, shallow, or irrelevant content.

REJECT if article matches ANY of these:
- beginner_tutorial    → "Getting started with X", "What is Y?", "Intro to Z", step-by-step for beginners
- opinion_fluff        → vague predictions, hot takes, "Top 10 reasons why...", listicles with no depth
- marketing_content    → product announcements disguised as articles, sponsored posts, press releases
- paywalled            → requires login, subscription wall, "members only"
- duplicate_story      → generic news rehash with no original analysis (e.g. just rephrasing a press release)
- low_depth            → less than 3 paragraphs of substance, no technical detail, no architecture insight

PASS if article is:
- Deep technical analysis or architecture patterns
- Research paper summary or breakdown  
- Engineering post-mortem or case study
- Emerging tool/framework with technical depth
- Industry shift with concrete technical implications
- Benchmark, performance analysis, or comparison

Respond ONLY with valid JSON. No explanation. No markdown. No preamble.

Format:
{
  "pass": true or false,
  "rejection_category": "<category or null>",
  "confidence": <float 0.0-1.0>,
  "reason": "<one line explanation>"
}

confidence rules:
  0.9-1.0 → very sure
  0.7-0.8 → fairly sure
  0.5-0.6 → borderline
"""


def guardrail_node(state: AgentState) -> AgentState:
    """
    Node 5 — Guardrail (LLM)

    Second LLM pass — quality gate.
    Rejects: fluff, beginner tutorials, marketing, paywalled, low-depth.

    Only high-confidence rejections (confidence >= 0.75) are dropped.
    Borderline articles pass through — better to keep than miss.

    Updates state:
        scored_articles → guardrail-passed articles only
        run_summary     → guardrail stats
    """
    articles = state.get("scored_articles", [])
    errors   = list(state.get("errors", []))

    console.rule("[bold cyan]GUARDRAIL NODE[/bold cyan]")
    console.print(f"\n[cyan]→ Running quality guardrails on {len(articles)} articles...[/cyan]\n")

    llm = _get_llm()

    passed:   list[Article] = []
    rejected: list[Article] = []

    for i, article in enumerate(articles, 1):
        try:
            result = _evaluate_guardrail(llm, article)

            passes     = result.get("pass", True)
            confidence = float(result.get("confidence", 0.5))
            category   = result.get("rejection_category") or ""
            reason     = result.get("reason", "")

            # only reject on HIGH confidence — don't drop borderline
            hard_reject = (not passes) and (confidence >= 0.75)

            if hard_reject:
                article.rejection_reason = f"{category}: {reason}"
                rejected.append(article)
                console.print(
                    f"  [red]✗[/red] [{i}/{len(articles)}] "
                    f"[bold]{article.title[:55]}[/bold]...\n"
                    f"       category=[red]{category}[/red]  "
                    f"confidence={confidence:.2f}  reason={reason[:60]}"
                )
            else:
                passed.append(article)
                flag = "[green]✓[/green]" if passes else "[yellow]~[/yellow] (borderline kept)"
                console.print(
                    f"  {flag} [{i}/{len(articles)}] "
                    f"[bold]{article.title[:55]}[/bold]..."
                )

        except Exception as e:
            errors.append(f"guardrail [{article.title[:40]}]: {str(e)}")
            console.print(
                f"  [yellow]~[/yellow] Guardrail error for "
                f"'{article.title[:40]}' — keeping article"
            )
            # on LLM error → keep (fail open, not closed)
            passed.append(article)

    run_summary = dict(state.get("run_summary", {}))
    run_summary["after_guardrail"]      = len(passed)
    run_summary["dropped_guardrail"]    = len(rejected)

    # breakdown by rejection category
    category_counts: dict[str, int] = {}
    for a in rejected:
        cat = a.rejection_reason.split(":")[0].strip()
        category_counts[cat] = category_counts.get(cat, 0) + 1

    if category_counts:
        console.print("\n  [dim]Rejection breakdown:[/dim]")
        for cat, count in category_counts.items():
            console.print(f"    [dim]• {cat}: {count}[/dim]")

    console.print(
        f"\n[bold green]Guardrail complete:[/bold green] "
        f"{len(passed)} passed / {len(rejected)} rejected"
    )

    return {
        **state,
        "scored_articles": passed,
        "errors": errors,
        "run_summary": run_summary,
    }


# ─────────────────────────────────────────────────────────────────
# LLM HELPERS
# ─────────────────────────────────────────────────────────────────

def _get_llm() -> AzureChatOpenAI:
    return AzureChatOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        azure_deployment=settings.azure_openai_deployment_name,
        openai_api_version=settings.azure_openai_api_version,
        api_key=settings.azure_openai_api_key,
        temperature=0,
        max_tokens=200,
    )


def _evaluate_guardrail(llm: AzureChatOpenAI, article: Article) -> dict:
    """Send article to LLM for guardrail evaluation."""
    user_content = f"""TITLE: {article.title}
SOURCE: {article.source}
TOPIC TAGS: {", ".join(article.topic_tags) or "unknown"}
SUMMARY: {article.summary[:600] or article.content_snippet[:600] or "No summary available."}
"""

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_content),
    ]

    response = llm.invoke(messages)
    return _parse_json_response(response.content)


def _parse_json_response(raw: str) -> dict:
    """Parse LLM JSON response safely. Strips markdown fences."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines   = cleaned.split("\n")
        cleaned = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
    return json.loads(cleaned)