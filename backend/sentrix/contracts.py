from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$"
    ),
]
Note = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=4, max_length=2000)
]
Role = Literal[
    "FRAUD_ANALYST", "SENIOR_ANALYST", "FRAUD_MANAGER", "RULES_ADMIN", "ADMIN"
]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Strict):
    login: Identifier
    password: Annotated[str, Field(min_length=1, max_length=128)]


class User(Login):
    name: Note
    role: Role

    @field_validator("password")
    @classmethod
    def password_length(cls, value):
        if len(value) < 12:
            raise ValueError("At least 12 characters")
        return value


class Event(Strict):
    source: Identifier
    external_id: Identifier
    account: Identifier
    amount: Annotated[int, Field(strict=True, gt=0, le=100_000_000_000)]
    currency: Literal["RUB"] = "RUB"
    category: Literal["GROCERY", "SERVICES", "TRAVEL", "ELECTRONICS", "TRANSFER"]
    channel: Literal["CARD", "WEB", "MOBILE"]
    recipient: Identifier
    occurred_at: AwareDatetime

    @field_validator("occurred_at", mode="before")
    @classmethod
    def explicit_timestamp(cls, value):
        if not isinstance(value, (datetime, str)) or (
            isinstance(value, str) and "T" not in value
        ):
            raise ValueError("Use an ISO 8601 timestamp with an offset")
        return value


class Batch(Strict):
    events: Annotated[list[Event], Field(min_length=1, max_length=100)]


class Csv(Strict):
    text: Annotated[str, Field(min_length=1, max_length=100_000)]


class CaseCommand(Strict):
    revision: Annotated[int, Field(strict=True, ge=1)]
    action: Literal[
        "assign",
        "triage",
        "investigate",
        "request_information",
        "resume",
        "submit",
        "return",
        "close",
        "comment",
        "evidence",
    ]
    reason: Note
    assignee: Identifier | None = None
    outcome: Literal["CONFIRMED", "FALSE_POSITIVE", "INCONCLUSIVE"] | None = None


class RuleDraft(Strict):
    parameters: dict[str, Annotated[int, Field(strict=True)]]
    reason: Note


class RuleSwitch(Strict):
    enabled: bool
    reason: Note
