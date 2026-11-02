"""Validated transport and extraction models. No model-generated workshop facts."""

from typing import Literal, Any
from datetime import date
from pydantic import BaseModel, Field, ConfigDict, field_validator

Objective = Literal["lateness", "quality", "fairness", "robustness", "hybrid"]


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=8000)
    session_id: str | None = Field(
        default=None, max_length=100, pattern=r"^[A-Za-z0-9_-]+$"
    )
    objective: Objective = "lateness"
    stages: bool = False

    @field_validator("message")
    @classmethod
    def meaningful(cls, value):
        if not value.strip():
            raise ValueError("请输入请求内容")
        return value.strip()


class Constraint(BaseModel):
    type: str
    value: str
    source: str
    scope: str = "current_request"


class ParsedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: str | None = Field(default=None, pattern=r"^ORD-\d{3}$")
    pieces: int | None = Field(default=None, ge=1, le=1000000)
    due_date: date | None = None
    excluded_workshops: list[str] = Field(default_factory=list)
    preferred_workshop: str | None = None
    constraints: list[Constraint] = Field(default_factory=list)
    allow_split: bool = False
    objective: str = "lateness"
    missing_fields: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    unanswerable_reason: str | None = None
    source_fields: dict[str, str] = Field(default_factory=dict)


class LLMExtraction(BaseModel):
    """Only language fields; the provider cannot supply capability/cost/queue facts."""

    model_config = ConfigDict(extra="forbid")
    order_id: str | None = Field(default=None, pattern=r"^ORD-\d{3}$")
    pieces: int | None = Field(default=None, ge=1, le=1000000)
    due_date: date | None = None
    excluded_workshops: list[str] = Field(default_factory=list)
    preferred_workshop: str | None = None
    objective: (
        Literal[
            "lateness",
            "quality",
            "fairness",
            "robustness",
            "hybrid",
            "fastest",
            "cheapest_on_time",
        ]
        | None
    ) = None
    allow_split: bool = False
    missing_fields: list[str] = Field(default_factory=list)
    ambiguity: str | None = None
    unanswerable_reason: str | None = None


class RecommendationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: str = Field(pattern=r"^ORD-\d{3}$")
    pieces: int | None = Field(default=None, ge=1, le=1000000)
    due_date: date | None = None
    objective: Objective = "lateness"
    excluded_workshops: list[str] = Field(default_factory=list, max_length=8)
    preferred_workshop: str | None = None
    stages: bool = False
    allow_split: bool = False


class ToolCall(BaseModel):
    name: Literal[
        "get_order",
        "list_workshops",
        "check_eligibility",
        "current_queue",
        "estimate_delivery",
        "overload_probe",
        "recommend_workshop",
    ]
    arguments: dict[str, Any] = Field(default_factory=dict)
