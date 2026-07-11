from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from .nodes import (
    analyze_node,
    classify_node,
    draft_node,
    route_node,
    search_kb_node,
)
from .state import AgentState


class SupportAgent:
    def __init__(self):
        self.graph = self._build_graph()
        self.checkpointer = MemorySaver()
        self.compiled = self.graph.compile(checkpointer=self.checkpointer)

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(AgentState)

        builder.add_node("classify", classify_node)
        builder.add_node("analyze", analyze_node)
        builder.add_node("search_kb", search_kb_node)
        builder.add_node("draft", draft_node)
        builder.add_node("route", route_node)

        builder.set_entry_point("classify")

        builder.add_edge("classify", "analyze")
        builder.add_edge("analyze", "search_kb")
        builder.add_edge("search_kb", "draft")
        builder.add_edge("draft", "route")

        builder.add_conditional_edges(
            "route",
            _disposition_router,
            {
                "respond": END,
                "escalate": END,
                "ask_more": "search_kb",
            },
        )

        return builder

    async def run(self, message: str, thread_id: str = "default") -> dict:
        config = {"configurable": {"thread_id": thread_id}}
        result = await self.compiled.ainvoke(
            {"messages": [("human", message)]},
            config=config,
        )
        return {
            "response": result.get("draft", ""),
            "category": result.get("category", ""),
            "urgency": result.get("urgency", ""),
            "sentiment": result.get("sentiment", ""),
            "route": result.get("route", ""),
            "confidence": result.get("confidence", 0.0),
        }


def _disposition_router(state: AgentState) -> str:
    route = state.get("route", "respond")
    if route in ("respond", "escalate"):
        return route
    return "ask_more"
