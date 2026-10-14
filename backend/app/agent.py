"""LangGraph workflow: retrieve policy -> search existing requests -> draft -> validate.

The graph can only call the two read-only tools and a draft model. It never writes to the
database; persistence and approval happen in the API layer.
"""
import json
import logging
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from . import tools
from .schemas import ProposalDraft

log = logging.getLogger("workflow.agent")


class AgentError(Exception):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


class State(TypedDict, total=False):
    request_id: int
    unit: str
    description: str
    policies: list[dict]
    similar: list[dict]
    raw: str
    draft: ProposalDraft
    error: tuple[str, str]


def build_graph(model):
    def lookup_policy(s: State):
        try:
            return {"policies": tools.lookup_policy(s["description"])}
        except Exception as e:
            log.error("tool lookup_policy failed: %s", type(e).__name__)
            return {"error": ("tool_failed", f"Policy lookup failed: {type(e).__name__}")}

    def search_requests(s: State):
        try:
            return {"similar": tools.search_requests(s["description"], exclude_id=s["request_id"])}
        except Exception as e:
            log.error("tool search_requests failed: %s", type(e).__name__)
            return {"error": ("tool_failed", f"Existing-request search failed: {type(e).__name__}")}

    def draft(s: State):
        try:
            return {"raw": model.draft(s["unit"], s["description"], s["policies"], s["similar"])}
        except Exception as e:
            log.error("model call failed: %s", type(e).__name__)
            return {"error": ("model_failed", f"Model call failed: {type(e).__name__}")}

    def validate(s: State):
        try:
            d = ProposalDraft.model_validate(json.loads(s["raw"]))
        except (json.JSONDecodeError, ValidationError, TypeError) as e:
            return {"error": ("invalid_output", f"Model output failed validation ({type(e).__name__})")}
        if d.policy_id not in {p["id"] for p in s["policies"]}:
            return {"error": ("invalid_output", f"Model cited policy {d.policy_id}, which was not retrieved")}
        return {"draft": d}

    def stop_on_error(nxt):
        return lambda s: END if s.get("error") else nxt

    g = StateGraph(State)
    for name, fn in [("lookup_policy", lookup_policy), ("search_requests", search_requests),
                     ("draft", draft), ("validate", validate)]:
        g.add_node(name, fn)
    g.add_edge(START, "lookup_policy")
    g.add_conditional_edges("lookup_policy", stop_on_error("search_requests"))
    g.add_conditional_edges("search_requests", stop_on_error("draft"))
    g.add_conditional_edges("draft", stop_on_error("validate"))
    g.add_edge("validate", END)
    return g.compile()


def run_agent(model, request_id: int, unit: str, description: str) -> ProposalDraft:
    out = build_graph(model).invoke({"request_id": request_id, "unit": unit, "description": description})
    if out.get("error"):
        raise AgentError(*out["error"])
    return out["draft"]
