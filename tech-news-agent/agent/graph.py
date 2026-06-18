from langgraph.graph import StateGraph, END

from agent.state import AgentState
from agent.nodes.ingest_node import ingest_node
from agent.nodes.date_filter_node import date_filter_node
from agent.nodes.dedup_node import dedup_node
from agent.nodes.topic_filter_node import topic_filter_node
from agent.nodes.guardrail_node import guardrail_node
from agent.nodes.rank_node import rank_node
from agent.nodes.output_node import output_node


# ─────────────────────────────────────────────────────────────────
# CONDITIONAL EDGES
# ─────────────────────────────────────────────────────────────────

def should_continue_after_ingest(state: AgentState) -> str:
    """
    After ingest — if nothing fetched, go straight to output
    (will render empty state panel, not crash).
    """
    if not state.get("raw_articles"):
        return "output"
    return "date_filter"


def should_continue_after_filter(state: AgentState) -> str:
    """
    After date_filter + dedup — if nothing left, skip LLM nodes.
    Saves cost — no point calling LLM on empty list.
    """
    if not state.get("filtered_articles"):
        return "output"
    return "topic_filter"


def should_continue_after_guardrail(state: AgentState) -> str:
    """
    After guardrail — if nothing passed, skip rank node.
    """
    if not state.get("scored_articles"):
        return "output"
    return "rank"


# ─────────────────────────────────────────────────────────────────
# GRAPH BUILDER
# ─────────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    """
    Wire all nodes into LangGraph.

    Flow:
        ingest
          ↓ (empty? → output)
        date_filter
          ↓
        dedup
          ↓ (empty? → output)
        topic_filter
          ↓
        guardrail
          ↓ (empty? → output)
        rank
          ↓
        output
          ↓
         END
    """
    graph = StateGraph(AgentState)

    # ── Register nodes ────────────────────────────────────────────
    graph.add_node("ingest",       ingest_node)
    graph.add_node("date_filter",  date_filter_node)
    graph.add_node("dedup",        dedup_node)
    graph.add_node("topic_filter", topic_filter_node)
    graph.add_node("guardrail",    guardrail_node)
    graph.add_node("rank",         rank_node)
    graph.add_node("output",       output_node)

    # ── Entry point ───────────────────────────────────────────────
    graph.set_entry_point("ingest")

    # ── Edges ─────────────────────────────────────────────────────

    # ingest → date_filter OR output (if empty)
    graph.add_conditional_edges(
        "ingest",
        should_continue_after_ingest,
        {
            "date_filter": "date_filter",
            "output":      "output",
        }
    )

    # date_filter → dedup (always)
    graph.add_edge("date_filter", "dedup")

    # dedup → topic_filter OR output (if empty)
    graph.add_conditional_edges(
        "dedup",
        should_continue_after_filter,
        {
            "topic_filter": "topic_filter",
            "output":       "output",
        }
    )

    # topic_filter → guardrail (always)
    graph.add_edge("topic_filter", "guardrail")

    # guardrail → rank OR output (if empty)
    graph.add_conditional_edges(
        "guardrail",
        should_continue_after_guardrail,
        {
            "rank":   "rank",
            "output": "output",
        }
    )

    # rank → output (always)
    graph.add_edge("rank", "output")

    # output → END
    graph.add_edge("output", END)

    return graph


def compile_graph():
    """Compile and return runnable graph."""
    graph = build_graph()
    return graph.compile()