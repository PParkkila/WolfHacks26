"""HTTP request and response models that are not domain or query models."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from agent.analysis.deviation import FeatureDeviation
from agent.auth import Principal, Role
from agent.clock import ClockState
from agent.query import ChangeReport

SessionId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,128}$")]
Message = Annotated[str, StringConstraints(min_length=1, max_length=4000)]


class PrincipalOut(BaseModel):
    user_id: str
    role: Role
    display_name: str
    participant_id: str | None

    @classmethod
    def of(cls, principal: Principal) -> "PrincipalOut":
        return cls(
            user_id=principal.user_id,
            role=principal.role,
            display_name=principal.display_name,
            participant_id=principal.participant_id,
        )


class LoginRequest(BaseModel):
    persona_id: str  # a `user_id` from GET /personas


class LoginResponse(BaseModel):
    token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    expires_in: int  # seconds
    principal: PrincipalOut


class ClockCommand(BaseModel):
    action: Literal["play", "pause", "speed", "seek"]
    seconds_per_hour: float | None = Field(default=None, gt=0)  # for "speed"
    to: datetime | None = None  # for "seek"


class ExplainResponse(BaseModel):
    change: ChangeReport
    # Where the person sits against everyone's newest windows; clinicians only.
    cohort_position: list[FeatureDeviation] | None


class ChatRequest(BaseModel):
    session_id: SessionId
    message: Message


class Health(BaseModel):
    db: bool
    llm: bool
    windows: int
    participants: int
    clock: ClockState | None
