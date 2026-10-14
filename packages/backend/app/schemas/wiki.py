"""Bounded Wiki write contracts; every replacement requires its expected head."""
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WikiSources(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_ids: list[UUID] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_sources(self) -> Self:
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("资料来源不能重复")
        return self


class WikiCreate(WikiSources):
    title: str = Field(min_length=1, max_length=200)


class WikiExpected(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision_id: UUID


class WikiEdit(WikiExpected):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=50000)


class WikiCompile(WikiSources):
    expected_revision_id: UUID
