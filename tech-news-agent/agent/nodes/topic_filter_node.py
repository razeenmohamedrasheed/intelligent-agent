import json
from rich.console import Console
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from agent.state import AgentState
from models.article import Article
from config.settings import settings

console = Console()

# ── Target topics for Senior Tech Architect ───────────────────────
ARCHITECT_TOPICS = [
    "Artificial Intelligence", "Generative AI", "LLMs", "Foundation Models",
    "Machine Learning", "MLOps", "AI Infrastructure",
    "Distributed Systems", "System Design", "Architecture Patterns",
    "Kubernetes", "Docker", "Container Orchestration",
    "Cloud Native", "Platform Engineering", "DevOps", "SRE",
    "Microservices", "Event-Driven Architecture", "Service Mesh",
    "Data Engineering", "Data Pipelines", "Streaming",
    "Vector Databases", "RAG", "AI Agents",
    "Observability", "FinOps", "Developer Productivity",
]

SYSTEM_PROMPT = """You are a strict content filter for a Senior Tech Architect news feed.

Your job: decide if an article is relevant to a Senior Tech Architect's reading list.

TARGET TOPICS:
{topics}

RELEVANT = article covers deep technical content, architecture patterns, 
emerging tools, industry shifts, research, or engineering practices 
in the above topics.

NOT RELEVANT = product launches unrelated to above, business/finance news, 
politics, sports, entertainment, celebrity tech news, pure marketing.

Respond ONLY with valid JSON. No explanation. No markdown. No preamble.

Format:
{{
  "relevant": true or false,
  "topic_tags": ["tag1", "tag2"],
  "relevance_score": <float 1-10>,
  "reason": "<one line why>"
}}

relevance_score rules:
  9-10 → core architect topic, deep technical
  7-8  → adjacent but valuable
  5-6  → loosely related, borderline
  1-4  → not relevant
""".format(topics="\n".join(f"- {t}" for t in ARCHITECT_TOPICS))


def topic_filter_node(state: AgentState) -> AgentState:
    """
    Node 4 — Topic Filter (LLM)

    For each article, asks gpt-4o-mini:
        - Is this relevant to a Senior Tech Architect?
        - What topic tags apply?
        - Relevance score 1-10?

    Drops articles below MIN_RELEVANCE_SCORE.

    Updates state:
        scored_articles → relevant articles with tags + scores
        run_summary     → topic filter stats
    """
    articles = state.get("filtered_articles", [])
    errors   = list(state.get("errors", []))

    console.rule("[bold cyan]TOPIC FILTER NODE[/bold cyan]")
    console.print(f"\n[cyan]→ Evaluating {len(articles)} articles with LLM...[/cyan]\n")

    llm = _get_llm()

    relevant:   list[Article] = []
    irrelevant: list[Article] = []

    for i, article in enumerate(articles, 1):
        try:
            result = _evaluate_article(llm, article)

            article.topic_tags      = result.get("topic_tags", [])
            article.relevance_score = float(result.get("relevance_score", 0.0))

            is_relevant = (
                result.get("relevant", False) and
                article.relevance_score >= settings.min_relevance_score
            )

            status = "[green]✓[/green]" if is_relevant else "[red]✗[/red]"
            tags   = ", ".join(article.topic_tags[:3]) or "none"

            console.print(
                f"  {status} [{i}/{len(articles)}] "
                f"[bold]{article.title[:55]}[/bold]...\n"
                f"       score={article.relevance_score:.1f}  "
                f"tags=[yellow]{tags}[/yellow]  "
                f"reason={result.get('reason', '')[:60]}"
            )

            if is_relevant:
                relevant.append(article)
            else:
                article.rejection_reason = f"off_topic: {result.get('reason', '')}"
                irrelevant.append(article)

        except Exception as e:
            errors.append(f"topic_filter [{article.title[:40]}]: {str(e)}")
            console.print(f"  [yellow]~[/yellow] LLM error for '{article.title[:40]}' — keeping article")
            # on LLM error → keep article (don't drop on infra failure)
            article.relevance_score = 5.0
            article.topic_tags      = []
            relevant.append(article)

    run_summary = dict(state.get("run_summary", {}))
    run_summary["after_topic_filter"]  = len(relevant)
    run_summary["dropped_off_topic"]   = len(irrelevant)

    console.print(
        f"\n[bold green]Topic filter complete:[/bold green] "
        f"{len(relevant)} relevant / {len(irrelevant)} dropped"
    )

    return {
        **state,
        "scored_articles": relevant,
        "errors": errors,
        "run_summary": run_summary,
    }


# ─────────────────────────────────────────────────────────────────
# LLM HELPERS
# ─────────────────────────────────────────────────────────────────

def _get_llm() -> AzureChatOpenAI:
    """Initialise Azure OpenAI LLM client."""
    return AzureChatOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        azure_deployment=settings.azure_openai_deployment_name,
        openai_api_version=settings.azure_openai_api_version,
        api_key=settings.azure_openai_api_key,
        temperature=0,        # deterministic — we want consistent filtering
        max_tokens=300,
    )


def _evaluate_article(llm: AzureChatOpenAI, article: Article) -> dict:
    """
    Send article title + summary to LLM for topic evaluation.
    Returns parsed JSON dict.
    """
    user_content = f"""TITLE: {article.title}
SOURCE: {article.source}
SUMMARY: {article.summary[:600] or article.content_snippet[:600] or "No summary available."}
"""

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_content),
    ]

    response = llm.invoke(messages)
    return _parse_json_response(response.content)


def _parse_json_response(raw: str) -> dict:
    """
    Parse LLM JSON response safely.
    Strips markdown fences if present.
    """
    cleaned = raw.strip()

    # strip ```json ... ``` fences
    if cleaned.startswith("```"):
        lines   = cleaned.split("\n")
        cleaned = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

    return json.loads(cleaned)