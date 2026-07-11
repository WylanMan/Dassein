import pytest
from api.agent.graph import SupportAgent, _disposition_router


class TestDispositionRouter:
    def test_respond_returns_respond(self):
        assert _disposition_router({"route": "respond", "messages": []}) == "respond"

    def test_escalate_returns_escalate(self):
        assert _disposition_router({"route": "escalate", "messages": []}) == "escalate"

    def test_ask_more_returns_ask_more(self):
        assert _disposition_router({"route": "ask_more", "messages": []}) == "ask_more"

    def test_empty_route_goes_to_ask_more(self):
        assert _disposition_router({"route": "", "messages": []}) == "ask_more"


class TestGraphStructure:
    def test_graph_compiles(self):
        agent = SupportAgent()
        assert agent.compiled is not None

    def test_graph_has_expected_nodes(self):
        agent = SupportAgent()
        nodes = list(agent.compiled.get_graph().nodes.keys())
        expected = {"classify", "analyze", "search_kb", "draft", "route"}
        for name in expected:
            assert name in nodes, f"Missing node: {name}"

    def test_graph_has_start_and_classify(self):
        agent = SupportAgent()
        graph = agent.compiled.get_graph()
        node_names = set(graph.nodes.keys())
        assert "__start__" in node_names
        assert "classify" in node_names
