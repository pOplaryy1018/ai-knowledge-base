from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class SourceCreate(BaseModel):
    knowledge_base_id: UUID
    name: str = Field(min_length=1, max_length=500)
    kind: Literal["document", "image", "git_local", "git_public"] = "document"
    config: dict[str, Any] = Field(default_factory=dict)


class SourceScopeUpdate(BaseModel):
    include_paths: list[str] = Field(default_factory=list, max_length=100)
