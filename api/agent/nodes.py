from langchain_core.messages import HumanMessage, SystemMessage

from .config import get_llm
from .state import AgentState

_llm = None


def get_llm_instance():
    global _llm
    if _llm is None:
        _llm = get_llm()
    return _llm

CATEGORIES = {
    "bug": "Technical issue, error, crash, broken feature",
    "billing": "Payment, invoice, refund, pricing, subscription",
    "account": "Login, password, permissions, profile, onboarding",
    "feature_request": "New capability, enhancement, integration request",
    "general": "How-to questions, documentation, best practices",
}


def classify_node(state: AgentState) -> dict:
    categories_desc = "\n".join(f"- {k}: {v}" for k, v in CATEGORIES.items())
    prompt = f"""Classify this customer support ticket into exactly one category.

Categories:
{categories_desc}

Respond with ONLY a JSON object with keys: category, subcategory, confidence (0.0-1.0)

Ticket: {state['messages'][-1].content}"""

    result = get_llm_instance().invoke([SystemMessage(content=prompt)])
    return _parse_classification(result.content)


def analyze_node(state: AgentState) -> dict:
    prompt = f"""Analyze the urgency and customer sentiment of this support ticket.

Respond with ONLY a JSON object with keys: urgency (critical/high/medium/low), sentiment (frustrated/neutral/positive), justification (one sentence)

Category: {state.get('category', 'unknown')}
Ticket: {state['messages'][-1].content}"""

    result = get_llm_instance().invoke([SystemMessage(content=prompt)])
    return _parse_analysis(result.content)


def search_kb_node(state: AgentState) -> dict:
    results = _get_faqs(state.get("category", "general"), state["messages"][-1].content)
    return {"kb_results": results, "faqs": [r["answer"] for r in results[:2]]}


def draft_node(state: AgentState) -> dict:
    faq_context = ""
    if state.get("faqs"):
        faq_context = "Relevant knowledge base articles:\n" + "\n---\n".join(
            state["faqs"]
        )

    prompt = f"""You are a customer support agent. Draft a helpful, concise reply.

{faq_context}

Category: {state.get('category', 'unknown')}
Urgency: {state.get('urgency', 'medium')}
Customer sentiment: {state.get('sentiment', 'neutral')}

Customer ticket:
{state['messages'][-1].content}

Draft a reply that:
1. Acknowledges the issue
2. Provides a clear next step or solution
3. Matches the urgency level
4. Is empathetic if sentiment is negative"""

    result = get_llm_instance().invoke([SystemMessage(content=prompt)])
    return {"draft": result.content.strip()}


def route_node(state: AgentState) -> dict:
    prompt = f"""Determine the disposition for this support ticket.

Category: {state.get('category', 'unknown')}
Urgency: {state.get('urgency', 'medium')}
Sentiment: {state.get('sentiment', 'neutral')}
Confidence: {state.get('confidence', 0.0)}
Draft reply: {state.get('draft', '')[:300]}

Choose one:
- respond: The draft answer is sufficient, reply directly
- escalate: Needs human review (high urgency, low confidence, complex issue)
- ask_more: Need more information from the customer before proceeding

Respond with ONLY a JSON object with keys: route, reason"""

    result = get_llm_instance().invoke([SystemMessage(content=prompt)])
    return _parse_route(result.content)


def _parse_classification(text: str) -> dict:
    try:
        import json
        data = json.loads(_extract_json(text))
        return {
            "category": data.get("category", "general"),
            "subcategory": data.get("subcategory", ""),
            "confidence": data.get("confidence", 0.0),
        }
    except Exception:
        return {"category": "general", "subcategory": "", "confidence": 0.0}


def _parse_analysis(text: str) -> dict:
    try:
        import json
        data = json.loads(_extract_json(text))
        return {
            "urgency": data.get("urgency", "medium"),
            "sentiment": data.get("sentiment", "neutral"),
        }
    except Exception:
        return {"urgency": "medium", "sentiment": "neutral"}


def _parse_route(text: str) -> dict:
    try:
        import json
        data = json.loads(_extract_json(text))
        return {
            "route": data.get("route", "respond"),
        }
    except Exception:
        return {"route": "respond"}


def _extract_json(text: str) -> str:
    import re
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else "{}"


def _get_faqs(category: str, query: str) -> list[dict]:
    faqs = {
        "bug": [
            {"question": "How to report a bug?", "answer": "Please include steps to reproduce, expected behavior, and actual behavior. Our team prioritises bugs by severity and will respond within 24 hours."},
            {"question": "Known issues?", "answer": "Check our status page at status.dassein.io for ongoing incidents. Most bugs are resolved within 2 business days."},
        ],
        "billing": [
            {"question": "Refund policy?", "answer": "We offer full refunds within 14 days of purchase. Pro-rated refunds after that. Refunds are processed within 5-7 business days."},
            {"question": "Update payment method?", "answer": "Go to Settings > Billing > Payment Methods to update your card or payment details."},
        ],
        "account": [
            {"question": "Reset password?", "answer": "Use the 'Forgot Password' link on the login page. A reset link will be sent to your registered email within 2 minutes."},
            {"question": "Change email?", "answer": "Go to Settings > Profile > Email to update your email address. A verification email will be sent to the new address."},
        ],
        "feature_request": [
            {"question": "How to submit feature request?", "answer": "Feature requests are reviewed monthly. Submit via the Feedback option in your dashboard or email suggestions@dassein.io."},
            {"question": "Feature timeline?", "answer": "Our roadmap is published at dassein.io/roadmap. Votes from users influence priority."},
        ],
        "general": [
            {"question": "Getting started?", "answer": "Check our documentation at docs.dassein.io for guides, tutorials, and API references."},
            {"question": "Contact support?", "answer": "Our support team is available Mon-Fri, 9am-6pm EST. Email support@dassein.io for assistance."},
        ],
    }
    return faqs.get(category, faqs["general"])
