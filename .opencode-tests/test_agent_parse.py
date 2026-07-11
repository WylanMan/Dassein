import pytest
from api.agent.nodes import _extract_json, _parse_classification, _parse_route, CATEGORIES


class TestExtractJson:
    def test_extracts_valid_json(self):
        text = 'Some text {"key": "value"} more text'
        assert _extract_json(text) == '{"key": "value"}'

    def test_returns_empty_for_no_json(self):
        assert _extract_json("no json here") == "{}"

    def test_handles_nested_json(self):
        text = '{"a": {"b": [1, 2]}}'
        assert _extract_json(text) == '{"a": {"b": [1, 2]}}'


class TestParseClassification:
    def test_parses_valid_response(self):
        result = _parse_classification('{"category": "bug", "subcategory": "login", "confidence": 0.95}')
        assert result["category"] == "bug"
        assert result["subcategory"] == "login"
        assert result["confidence"] == 0.95

    def test_defaults_on_invalid(self):
        result = _parse_classification("invalid")
        assert result["category"] == "general"
        assert result["confidence"] == 0.0


class TestParseRoute:
    def test_parses_respond(self):
        result = _parse_route('{"route": "respond", "reason": "clear answer"}')
        assert result["route"] == "respond"

    def test_parses_escalate(self):
        result = _parse_route('{"route": "escalate"}')
        assert result["route"] == "escalate"

    def test_defaults_on_invalid(self):
        result = _parse_route("garbage")
        assert result["route"] == "respond"


class TestCategories:
    def test_has_all_five_categories(self):
        assert set(CATEGORIES.keys()) == {"bug", "billing", "account", "feature_request", "general"}

    def test_each_category_has_description(self):
        for k, v in CATEGORIES.items():
            assert isinstance(v, str) and len(v) > 5
