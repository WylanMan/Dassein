from typing import Annotated, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    category: str
    subcategory: str
    urgency: str
    sentiment: str
    kb_results: list[dict]
    draft: str
    route: str
    confidence: float
    faqs: list[str]
