"""Public graph projection responses after PostgreSQL verification."""

from uuid import UUID

from pydantic import BaseModel


class GraphRelationResponse(BaseModel):
    id: str
    subject: str
    subject_type: str
    predicate: str
    object: str
    object_type: str
    quote: str
    document_id: UUID
    revision_id: UUID
    locator: dict[str, str | int]


class GraphRelationsResponse(BaseModel):
    revision_id: UUID
    items: list[GraphRelationResponse]
    truncated: bool
