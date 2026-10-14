from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Urgency = Literal["emergency", "urgent", "routine", "low"]


class ProposalDraft(BaseModel):
    """Structured model output. Unknown fields (e.g. an 'approved' flag) are rejected."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    urgency: Urgency
    category: str = Field(min_length=1, max_length=60)
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1000)
    reasoning: str = Field(min_length=1, max_length=1500)
    policy_id: str = Field(pattern=r"^P-\d+$")


class RequestIn(BaseModel):
    unit: str = Field(min_length=1, max_length=20)
    description: str = Field(min_length=5, max_length=1000)


class LoginIn(BaseModel):
    username: str
    password: str


class Edits(BaseModel):
    """Reviewer edits applied at approval time."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    urgency: Urgency | None = None
    category: str | None = Field(default=None, min_length=1, max_length=60)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, min_length=1, max_length=1000)


class RejectIn(BaseModel):
    reason: str = Field(min_length=1, max_length=300)
