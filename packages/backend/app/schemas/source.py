from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class SourceCreate(BaseModel):
    knowledge_base_id: UUID
    name: str = Field(min_length=1, max_length=500)
    kind: Literal["document"] = "document"
