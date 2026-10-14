import pytest
from pydantic import ValidationError

from app import agent, policy, tools
from app.schemas import Edits, ProposalDraft, RequestIn
from conftest import GOOD, FakeModel


def test_policy_lookup_matches_keywords(env):
    assert policy.lookup_policy("the kitchen tap is dripping")[0].id == "P-3"
    assert policy.lookup_policy("I smell gas")[0].id == "P-1"


def test_policy_lookup_falls_back_when_nothing_matches(env):
    assert [p.id for p in policy.lookup_policy("xyzzy plugh")] == ["P-6"]


def test_output_validation_accepts_good_and_rejects_bad():
    assert ProposalDraft.model_validate(GOOD).urgency == "routine"
    with pytest.raises(ValidationError):
        ProposalDraft.model_validate({**GOOD, "urgency": "whenever"})
    with pytest.raises(ValidationError):  # model-supplied approval flag is not accepted
        ProposalDraft.model_validate({**GOOD, "approved": True})
    with pytest.raises(ValidationError):
        ProposalDraft.model_validate({k: v for k, v in GOOD.items() if k != "reasoning"})


def test_invalid_input_rejected():
    with pytest.raises(ValidationError):
        RequestIn(unit="", description="leak")
    with pytest.raises(ValidationError):
        Edits(urgency="emergency", approved=True)


def test_agent_rejects_policy_not_retrieved(client):
    with pytest.raises(agent.AgentError) as e:
        agent.run_agent(FakeModel({**GOOD, "policy_id": "P-99"}), 1, "A-1", "tap leak")
    assert e.value.kind == "invalid_output"


def test_agent_reports_non_json(client):
    with pytest.raises(agent.AgentError) as e:
        agent.run_agent(FakeModel("not json"), 1, "A-1", "tap leak")
    assert e.value.kind == "invalid_output"


def test_search_tool_is_read_only(env, client):
    from app import db
    conn = db.connect_readonly()
    with pytest.raises(Exception):
        conn.execute("DELETE FROM requests")
    assert tools.search_requests("tap dripping")  # seeded data found


def test_duplicate_approval_creates_one_order(api):
    h = api.login()
    r = api.c.post("/api/requests", json={"unit": "A-1", "description": "tap is dripping"}, headers=h).json()
    p = api.c.post(f"/api/requests/{r['id']}/propose", headers=h).json()
    first = api.c.post(f"/api/proposals/{p['id']}/approve", headers=h)
    second = api.c.post(f"/api/proposals/{p['id']}/approve", headers=h)
    assert first.json()["duplicate"] is False and second.json()["duplicate"] is True
    assert first.json()["work_order"]["id"] == second.json()["work_order"]["id"]
    assert len(api.c.get("/api/work-orders", headers=h).json()) == 1
