"""Application messages, carried inside standard A2A data parts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Case = Literal["medium", "hard"]
Mode = Literal["vulnerable", "fixed"]


class ReviewRecord(BaseModel):
    """A reviewer-owned decision and the exact reviewed input bytes."""

    model_config = ConfigDict(extra="forbid")

    review_id: str
    case: Case
    subject: str
    decision: Literal["approve", "reject"]
    explanation: str
    conditions: list[str]
    created_at: str
    policy_version: str = "basharena-pipeline-v1"
    digests: dict[str, str] = Field(default_factory=dict)
    snapshots: dict[str, str] = Field(default_factory=dict)
    plan: list[str] = Field(default_factory=list)

    def public(self) -> dict[str, object]:
        """Return the decision without embedding artifact contents."""
        return self.model_dump(exclude={"snapshots"})
