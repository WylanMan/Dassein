import pytest
from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, AIMessage


class MockState(TypedDict):
    messages: Annotated[list, add_messages]
    category: str
    urgency: str
    sentiment: str
    draft: str
    route: str
    confidence: float


def test_state_schema_has_required_keys():
    keys = MockState.__annotations__.keys()
    assert "messages" in keys
    assert "category" in keys
    assert "urgency" in keys
    assert "route" in keys


def test_add_messages_appends():
    msgs = [HumanMessage(content="hello")]
    result = add_messages(msgs, AIMessage(content="hi"))
    assert len(result) == 2
    assert result[1].content == "hi"


def test_state_defaults_are_empty_strings():
    state = MockState(messages=[], category="", urgency="", sentiment="", draft="", route="", confidence=0.0)
    assert state["category"] == ""
    assert state["route"] == ""
    assert state["confidence"] == 0.0
