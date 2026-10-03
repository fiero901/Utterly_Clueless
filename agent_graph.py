"""LangGraph orchestration for the JeevanRoute agent workflow."""

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from routing_agent import route
from triage_agent import triage_turn


class AgentState(TypedDict, total=False):
    history: list[dict[str, Any]]
    district: str
    coords: tuple[float, float] | None
    memory_context: str
    text: str
    triage: dict[str, Any] | None
    route_block: str
    error: str


def triage_node(state: AgentState) -> AgentState:
    """Run the conversational triage agent and capture its structured tool result."""
    try:
        text, triage = triage_turn(
            state.get("history", []),
            memory_context=state.get("memory_context", ""),
        )
        return {"text": text or "", "triage": triage}
    except Exception as exc:
        return {"error": str(exc).splitlines()[0][:120]}


def route_node(state: AgentState) -> AgentState:
    """Run hospital routing after triage completes."""
    try:
        result = route(
            state["triage"],
            district=state.get("district", ""),
            origin_coords=state.get("coords"),
        )
        return {"route_block": result.get("block", "")}
    except Exception as exc:
        return {
            "route_block": (
                f"\n\n🏥 _Hospital routing unavailable ({exc}). Call **102**._"
            )
        }


def after_triage(state: AgentState) -> str:
    if state.get("error") or not state.get("triage"):
        return "finish"
    return "route"


def build_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("triage", triage_node)
    workflow.add_node("route", route_node)
    workflow.add_edge(START, "triage")
    workflow.add_conditional_edges(
        "triage",
        after_triage,
        {"route": "route", "finish": END},
    )
    workflow.add_edge("route", END)
    return workflow.compile()


jeevanroute_graph = build_graph()
