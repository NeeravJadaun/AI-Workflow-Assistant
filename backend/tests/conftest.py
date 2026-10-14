import json

import pytest
from fastapi.testclient import TestClient

from app import config, main, models


class FakeModel:
    mode = "llm"

    def __init__(self, output):
        self.output = output

    def draft(self, unit, description, policies, similar):
        if isinstance(self.output, Exception):
            raise self.output
        return self.output if isinstance(self.output, str) else json.dumps(self.output)


GOOD = {"urgency": "routine", "category": "plumbing", "title": "Fix dripping tap",
        "description": "Replace washer on kitchen tap.", "reasoning": "Contained leak per policy.",
        "policy_id": "P-3"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


@pytest.fixture
def client(env):
    with TestClient(main.app) as c:
        yield c


class Session:
    def __init__(self, client):
        self.c = client
        self.model_output = GOOD
        main.app.dependency_overrides[main.get_model_factory] = lambda: (
            lambda mode: models.DemoModel() if mode == "demo" else FakeModel(self.model_output))

    def login(self, user="reviewer", pw="reviewer123"):
        r = self.c.post("/api/auth/login", json={"username": user, "password": pw})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
def api(client):
    yield Session(client)
    main.app.dependency_overrides.clear()
