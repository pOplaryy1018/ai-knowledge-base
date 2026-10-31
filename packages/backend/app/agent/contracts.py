"""Shared data contracts for agent execution and task events."""

from collections.abc import Mapping
from datetime import datetime
from math import isfinite
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_serializer, field_validator


def _check_finite_json(value: JsonValue) -> None:
    if isinstance(value, float) and not isfinite(value):
        raise ValueError("JSON numbers must be finite")
    if isinstance(value, dict):
        for item in value.values():
            _check_finite_json(item)
    elif isinstance(value, list):
        for item in value:
            _check_finite_json(item)


class AgentContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("arguments", "data", "payload", check_fields=False)
    @classmethod
    def validate_finite_json(cls, value: dict[str, JsonValue] | None) -> dict[str, JsonValue] | None:
        if value is not None:
            _check_finite_json(value)
        return value

    @field_serializer("arguments", "data", "payload", check_fields=False)
    def serialize_finite_json(self, value: dict[str, JsonValue] | None) -> dict[str, JsonValue] | None:
        if value is not None:
            _check_finite_json(value)
        return value


class RuntimeContext(AgentContract):
    """Trusted execution context constructed by the server, never by the model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    owner_id: str
    task_id: str
    source_versions: Mapping[str, str]

    @field_validator("source_versions")
    @classmethod
    def freeze_source_versions(cls, value: Mapping[str, str]) -> Mapping[str, str]:
        return MappingProxyType(dict(value))

    @field_serializer("source_versions")
    def serialize_source_versions(self, value: Mapping[str, str]) -> dict[str, str]:
        return dict(value)


class ToolRequest(AgentContract):
    call_id: str
    name: str
    arguments: dict[str, JsonValue]


class ToolResult(AgentContract):
    call_id: str
    ok: bool
    data: dict[str, JsonValue] | None = None
    error: str | None = None


class ModelTurn(AgentContract):
    text: str | None = None
    tool_calls: list[ToolRequest] = Field(default_factory=list)


class TaskEvent(AgentContract):
    task_id: str
    seq: int = Field(ge=1, strict=True)
    type: str
    payload: dict[str, JsonValue]
    created_at: datetime
