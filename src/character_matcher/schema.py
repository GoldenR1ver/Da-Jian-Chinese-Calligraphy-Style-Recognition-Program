from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    left: int
    top: int
    width: int
    height: int


class GlyphCandidate(BaseModel):
    author_id: Optional[str] = None
    author_name: Optional[str] = None
    style: Optional[str] = None
    dynasty: Optional[str] = None

    # provenance / linkage (db ids, source urls, etc.)
    sample_id: Optional[str] = None
    work_id: Optional[str] = None
    source: Optional[str] = None
    license: Optional[str] = None

    # similarity
    score: float = Field(ge=0, le=100)
    method: Literal["cv_baseline", "embedding_ann", "hybrid"] = "cv_baseline"
    extras: dict[str, Any] = Field(default_factory=dict)


class SingleCharMatch(BaseModel):
    char: str = Field(min_length=1, max_length=1)
    location: Optional[BoundingBox] = None
    candidates: list[GlyphCandidate] = Field(default_factory=list)


class AuthorAttribution(BaseModel):
    author_id: Optional[str] = None
    author_name: Optional[str] = None
    dynasty: Optional[str] = None

    score: float = Field(ge=0, le=100)
    votes: int = Field(ge=0)
    evidence_chars: list[str] = Field(default_factory=list)
    extras: dict[str, Any] = Field(default_factory=dict)


class MatchBundle(BaseModel):
    version: str = "0.1.0"
    image_path: Optional[str] = None
    ocr_engine: Optional[str] = None

    chars: list[SingleCharMatch] = Field(default_factory=list)
    authors: list[AuthorAttribution] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)

