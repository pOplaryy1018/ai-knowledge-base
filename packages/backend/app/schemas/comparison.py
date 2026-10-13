"""Bounded data-only comparison output; model-supplied source metadata is forbidden."""
from pydantic import BaseModel, ConfigDict, Field, StrictInt


class ComparisonCellDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=1000)
    citation_indices: list[StrictInt] = Field(max_length=3)


class ComparisonRowDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    dimension: str = Field(min_length=1, max_length=80)
    cells: list[ComparisonCellDraft] = Field(max_length=4)


class ComparisonDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: list[ComparisonRowDraft] = Field(min_length=1, max_length=8)
