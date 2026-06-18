import json
from rich.console import Console
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from agent.state import AgentState
from models.article import Article
from tools.scorer_tool import score_articles, explain_score
from config.settings import settings

console = Console()


SYSTEM_PROMPT = """You are a ranking assistant for a Senior Tech Architect news feed.

Your job: score an article on how valuable it is for a Senior Tech Architect.

SCORING CRITERIA (each 1-10):

1. technical_depth
   10 → deep architecture analysis, benchmarks, research-level
   7  → solid engineering post, good technical detail
   4  → surface overview, no deep insight
   1  → no technical content

2. architect_relevance  
   10 → directly applicable — system design, distributed systems, LLMs, cloud-native
   7  → adjacent — useful context, emerging tools
   4  → loosely related
   1  → not relevant to architect role

3. novelty
   10 → new research, new paradigm, breaking industry shift
   7  → new tool/approach worth knowing
   4  → incremental update
   1  → rehash of known content

Respond ONLY with valid JSON. No markdown. No preamble.

Format:
{
  "technical_depth": <int 1-10>,
  "architect_relevance": <int 1-10>,
  "novelty": <int 1-10>,
  "overall_relevance_score": <float 1-10>,
  "one_line_summary": "<crisp 1-sentence summary for architect audience>"
}

overall_relevance_score = weighted avg:
  (technical_depth * 0.4) + (architect_relevance * 0.4) + (novelty * 0.2)
"""


def rank_node(state: AgentState) -> AgentState:
    """
    Node 6 — Rank (LLM + scorer_tool)

    Two-step ranking:
        Step 1 → LLM scores each article on 3 dimensions
        Step 2 → scorer_tool computes weighted final_score
                 (relevance + recency + source credibility)

    Surfaces top N articles sorted by final_score.

    Updates state:
        ranked_articles → top N articles, sorted
        run_summary     → rank stats
    """
    articles = state.get("scored_articles", [])
    errors   = list(state.get("errors", []))

    console.rule("[bold cyan]RANK NODE[/bold cyan]")
    console.print(f"\n[cyan]→ Ranking {len(articles)} articles with LLM...[/cyan]\n")

    llm = _get_llm()

    for i, article in enumerate(articles, 1):
        try:
            result = _score_article(llm, article)

            # attach LLM scores
            article.relevance_score = float(result.get("overall_relevance_score", 5.0))

            # override summary with LLM-generated crisp architect summary
            llm_summary = result.get("one_line_summary", "")
            if llm_summary:
                article.summary = llm_summary

            # attach sub-scores to tags for display
            depth     = result.get("technical_depth", 0)
            relevance = result.get("architect_relevance", 0)
            novelty   = result.get("novelty", 0)

            console.print(
                f"  [green]✓[/green] [{i}/{len(articles)}] "
                f"[bold]{article.title[:55]}[/bold]...\n"
                f"       depth={depth}  relevance={relevance}  "
                f"novelty={novelty}  "
                f"overall=[bold yellow]{article.relevance_score:.1f}[/bold yellow]"
            )

        except Exception as e:
            errors.append(f"rank [{article.title[:40]}]: {str(e)}")
            console.print(
                f"  [yellow]~[/yellow] LLM rank error for "
                f"'{article.title[:40]}' — using default score"
            )
            article.relevance_score = 5.0

    # ── Step 2: compute weighted final_score via scorer_tool ──────
    ranked = score_articles(articles)  # attaches final_score + sorts

    # ── Cap at MAX_ARTICLES_OUTPUT ────────────────────────────────
    top_n  = ranked[:settings.max_articles_output]

    run_summary = dict(state.get("run_summary", {}))
    run_summary["after_ranking"]  = len(ranked)
    run_summary["final_output"]   = len(top_n)

    console.print(
        f"\n[bold green]Ranking complete:[/bold green] "
        f"Top {len(top_n)} articles surfaced "
        f"(from {len(ranked)} candidates)"
    )

    return {
        **state,
        "ranked_articles": top_n,
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
        max_tokens=250,
    )


def _score_article(llm: AzureChatOpenAI, article: Article) -> dict:
    """Send article to LLM for multi-dimension scoring."""
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
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines   = cleaned.split("\n")
        cleaned = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
    return json.loads(cleaned)