from langgraph.graph import StateGraph, END

from agent.state import AgentState
from agent.nodes.ingest_node import ingest_node
from agent.nodes.date_filter_node import date_filter_node
from agent.nodes.dedup_node import dedup_node
from agent.nodes.keyword_filter_node import keyword_filter_node
from agent.nodes.topic_filter_node import topic_filter_node
from agent.nodes.guardrail_node import guardrail_node
from agent.nodes.rank_node import rank_node
from agent.nodes.output_node import output_node


# ─────────────────────────────────────────────────────────────────
# CONDITIONAL EDGES
# ─────────────────────────────────────────────────────────────────

def should_continue_after_ingest(state: AgentState) -> str:
    if not state.get("raw_articles"):
        return "output"
    return "date_filter"


def should_continue_after_dedup(state: AgentState) -> str:
    if not state.get("filtered_articles"):
        return "output"
    return "keyword_filter"


def should_continue_after_keyword_filter(state: AgentState) -> str:
    if not state.get("filtered_articles"):
        return "output"
    return "topic_filter"


def should_continue_after_guardrail(state: AgentState) -> str:
    if not state.get("scored_articles"):
        return "output"
    return "rank"


# ─────────────────────────────────────────────────────────────────
# GRAPH BUILDER
# ─────────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    """
    Flow:
        ingest
          ↓ (empty? → output)
        date_filter
          ↓
        dedup
          ↓ (empty? → output)
        keyword_filter    ← fast pre-LLM keyword drop
          ↓ (empty? → output)
        topic_filter      ← LLM
          ↓
        guardrail         ← LLM
          ↓ (empty? → output)
        rank              ← LLM
          ↓
        output → END
    """
    graph = StateGraph(AgentState)

    graph.add_node("ingest",         ingest_node)
    graph.add_node("date_filter",    date_filter_node)
    graph.add_node("dedup",          dedup_node)
    graph.add_node("keyword_filter", keyword_filter_node)
    graph.add_node("topic_filter",   topic_filter_node)
    graph.add_node("guardrail",      guardrail_node)
    graph.add_node("rank",           rank_node)
    graph.add_node("output",         output_node)

    graph.set_entry_point("ingest")

    graph.add_conditional_edges(
        "ingest", should_continue_after_ingest,
        {"date_filter": "date_filter", "output": "output"}
    )
    graph.add_edge("date_filter", "dedup")
    graph.add_conditional_edges(
        "dedup", should_continue_after_dedup,
        {"keyword_filter": "keyword_filter", "output": "output"}
    )
    graph.add_conditional_edges(
        "keyword_filter", should_continue_after_keyword_filter,
        {"topic_filter": "topic_filter", "output": "output"}
    )
    graph.add_edge("topic_filter", "guardrail")
    graph.add_conditional_edges(
        "guardrail", should_continue_after_guardrail,
        {"rank": "rank", "output": "output"}
    )
    graph.add_edge("rank", "output")
    graph.add_edge("output", END)

    return graph


def compile_graph():
    graph = build_graph()
    return graph.compile()