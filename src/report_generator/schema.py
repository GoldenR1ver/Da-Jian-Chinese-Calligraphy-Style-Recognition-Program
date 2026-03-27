from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ReportStyleDimension(BaseModel):
    name: str
    weight: float = Field(ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)


class ReportEvidenceItem(BaseModel):
    char: str = Field(min_length=1, max_length=1)
    author_name: Optional[str] = None
    score: float = Field(ge=0, le=100)
    why: list[str] = Field(default_factory=list)
    extras: dict[str, Any] = Field(default_factory=dict)


class StyleReport(BaseModel):
    schema_version: str = "0.1.0"
    generator: Literal["rule_based", "llm", "hybrid"] = "rule_based"

    summary: str
    top_authors: list[str] = Field(default_factory=list)
    style_dimensions: list[ReportStyleDimension] = Field(default_factory=list)
    evidence: list[ReportEvidenceItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)

