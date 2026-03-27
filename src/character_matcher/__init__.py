"""Character matching & retrieval layer."""

from .matcher import MatcherConfig, enrich_bundle_with_db_matches
from .schema import AuthorAttribution, BoundingBox, GlyphCandidate, MatchBundle, SingleCharMatch

__all__ = [
    "MatcherConfig",
    "enrich_bundle_with_db_matches",
    "AuthorAttribution",
    "BoundingBox",
    "GlyphCandidate",
    "MatchBundle",
    "SingleCharMatch",
]

