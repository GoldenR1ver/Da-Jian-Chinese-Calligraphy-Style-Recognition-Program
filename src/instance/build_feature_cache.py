"""Offline build of glyph_features table so first-run matching is faster."""

from __future__ import annotations

import argparse
from typing import Optional

from ..character_matcher.feature_index import (
    ensure_feature_table,
    extract_feature,
    glyph_sample_to_gray,
    load_sample_feature,
    upsert_sample_feature,
)
from ..character_matcher.repository import db_connection, fetch_glyph_sample_by_id


def build_feature_cache(
    db_path: Optional[str] = None,
    *,
    skip_existing: bool = True,
    limit: Optional[int] = None,
    commit_every: int = 100,
) -> tuple[int, int, int]:
    """Return (built_count, skipped_count, failed_count)."""
    built = 0
    skipped = 0
    failed = 0
    with db_connection(db_path) as conn:
        ensure_feature_table(conn)
        cur = conn.execute(
            "SELECT character_id FROM characters ORDER BY character_id"
        )
        rows = cur.fetchall()
        if limit is not None:
            rows = rows[: int(limit)]
        for row in rows:
            sid = int(row["character_id"])
            if skip_existing and load_sample_feature(conn, sid) is not None:
                skipped += 1
                continue
            sample = fetch_glyph_sample_by_id(conn, sid)
            if sample is None:
                failed += 1
                continue
            gray = glyph_sample_to_gray(sample)
            if gray is None:
                failed += 1
                continue
            feat = extract_feature(gray)
            upsert_sample_feature(conn, sid, feat)
            built += 1
            if built % commit_every == 0:
                conn.commit()
        conn.commit()
    return built, skipped, failed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Precompute and store glyph features in glyph_features table."
    )
    parser.add_argument("--db-path", default=None, help="Optional custom database path")
    parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="Recompute all rows even if a feature already exists",
    )
    parser.add_argument("--limit", type=int, default=None, help="Process at most N rows")
    parser.add_argument(
        "--commit-every",
        type=int,
        default=100,
        help="Commit after this many successful inserts",
    )
    args = parser.parse_args()
    built, skipped, failed = build_feature_cache(
        db_path=args.db_path,
        skip_existing=not args.no_skip_existing,
        limit=args.limit,
        commit_every=args.commit_every,
    )
    print(f"Built: {built}, skipped (already cached): {skipped}, failed (no raster): {failed}")


if __name__ == "__main__":
    main()
