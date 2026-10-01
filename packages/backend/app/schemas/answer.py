from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AnswerSave(BaseModel):
    message_id: UUID


class CandidateAccept(BaseModel):
    candidate_id: UUID
    expected_answer_revision_id: UUID
    expected_source_versions: dict[UUID, UUID]


class ReviewDecision(BaseModel):
    decision: Literal["retain"]
    note: str = Field(min_length=1, max_length=2000)
