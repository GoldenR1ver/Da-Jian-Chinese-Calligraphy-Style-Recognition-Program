from __future__ import annotations

import os
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from ..style_analyzer import combined_similarity
from .feature_index import extract_feature, glyph_sample_to_gray, rank_candidates_by_feature, render_svg_to_png
from .repository import GlyphSample, db_connection, fetch_glyph_samples_by_char, normalize_author_name
from .schema import AuthorAttribution, GlyphCandidate, MatchBundle


@dataclass
class MatcherConfig:
    sample_limit_per_char: int = 120
    feature_prefilter_limit: int = 40
    top_k_per_char: int = 5
    top_n_authors: int = 5
    min_score_to_vote: float = 45.0
    db_path: Optional[str] = None


def _safe_crop(gray_image: np.ndarray, left: int, top: int, width: int, height: int) -> Optional[np.ndarray]:
    h, w = gray_image.shape[:2]
    x1 = max(0, left)
    y1 = max(0, top)
    x2 = min(w, left + width)
    y2 = min(h, top + height)
    if x2 <= x1 or y2 <= y1:
        return None
    crop = gray_image[y1:y2, x1:x2]
    return crop if crop.size > 0 else None


def _write_temp_png_from_array(image: np.ndarray) -> Optional[Path]:
    fd, path = tempfile.mkstemp(suffix=".png")
    # Windows cannot unlink a file while its descriptor is still open.
    os.close(fd)
    Path(path).unlink(missing_ok=True)
    ok = cv2.imwrite(path, image)
    if not ok:
        return None
    return Path(path)


def _sample_to_png_path(sample: GlyphSample) -> tuple[Optional[Path], str]:
    if sample.image_data:
        arr = np.frombuffer(sample.image_data, dtype=np.uint8)
        image = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        if image is not None:
            path = _write_temp_png_from_array(image)
            return path, "image_data"
    if sample.svg:
        png_bytes = render_svg_to_png(sample.svg)
        if png_bytes:
            arr = np.frombuffer(png_bytes, dtype=np.uint8)
            image = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
            if image is not None:
                path = _write_temp_png_from_array(image)
                return path, "svg_rendered"
        return None, "svg_unavailable"
    return None, "no_visual_data"


def _is_cjk_char(ch: str) -> bool:
    if not ch:
        return False
    cp = ord(ch)
    return (
        0x4E00 <= cp <= 0x9FFF
        or 0x3400 <= cp <= 0x4DBF
        or 0x20000 <= cp <= 0x2A6DF
        or 0x2A700 <= cp <= 0x2B73F
        or 0x2B740 <= cp <= 0x2B81F
        or 0x2B820 <= cp <= 0x2CEAF
        or 0xF900 <= cp <= 0xFAFF
    )


def _confidence_weight(score: float, min_score_to_vote: float) -> float:
    """
    Convert raw score to confidence weight in [0, 1].

    Only scores above min_score_to_vote contribute; higher scores are amplified
    with a quadratic curve to suppress weak candidates.
    """
    if score < min_score_to_vote:
        return 0.0
    span = max(1e-6, 100.0 - float(min_score_to_vote))
    normalized = max(0.0, min(1.0, (float(score) - float(min_score_to_vote)) / span))
    return normalized * normalized


def _pick_single_char_vote(
    candidates: list[GlyphCandidate], min_score_to_vote: float
) -> tuple[Optional[str], float, float]:
    """
    Pick one author vote for a single character.

    Strategy:
    1) Remove low-score/empty-author candidates.
    2) Deduplicate by author (keep author's best candidate for this char).
    3) Use confidence-weighted score to select only one winning author.
    """
    per_author_best: dict[str, GlyphCandidate] = {}
    for candidate in candidates:
        if not candidate.author_name or candidate.score < min_score_to_vote:
            continue
        prev = per_author_best.get(candidate.author_name)
        if prev is None or candidate.score > prev.score:
            per_author_best[candidate.author_name] = candidate

    if not per_author_best:
        return None, 0.0, 0.0

    best_author = None
    best_score = 0.0
    best_weight = 0.0
    best_weighted_score = -1.0
    for author_name, best_candidate in per_author_best.items():
        weight = _confidence_weight(best_candidate.score, min_score_to_vote)
        weighted_score = best_candidate.score * weight
        if weighted_score > best_weighted_score:
            best_author = author_name
            best_score = float(best_candidate.score)
            best_weight = weight
            best_weighted_score = weighted_score

    if best_author is None or best_weight <= 0:
        return None, 0.0, 0.0
    return best_author, best_score, best_weight


def enrich_bundle_with_db_matches(bundle: MatchBundle, config: Optional[MatcherConfig] = None) -> MatchBundle:
    cfg = config or MatcherConfig()
    if not bundle.image_path:
        return bundle

    source = cv2.imread(bundle.image_path, cv2.IMREAD_GRAYSCALE)
    if source is None:
        return bundle

    with db_connection(cfg.db_path) as conn:
        author_stats: dict[str, dict] = defaultdict(
            lambda: {"weighted_score_sum": 0.0, "confidence_sum": 0.0, "votes": 0, "chars": set()}
        )
        filtered_non_cjk_chars: list[str] = []
        missing_in_db_chars: list[str] = []
        matched_char_count = 0
        db_covered_char_count = 0
        total_char_count = len(bundle.chars)
        cjk_char_count = 0
        for ch in bundle.chars:
            if not ch.char or not ch.location:
                continue
            if not _is_cjk_char(ch.char):
                filtered_non_cjk_chars.append(ch.char)
                continue
            cjk_char_count += 1

            crop = _safe_crop(
                source,
                left=ch.location.left,
                top=ch.location.top,
                width=ch.location.width,
                height=ch.location.height,
            )
            if crop is None:
                continue

            user_char_path = _write_temp_png_from_array(crop)
            if user_char_path is None:
                continue

            samples = fetch_glyph_samples_by_char(conn, ch.char, limit=cfg.sample_limit_per_char)
            if not samples:
                missing_in_db_chars.append(ch.char)
                continue
            db_covered_char_count += 1
            if samples:
                user_feature = extract_feature(crop)
                samples = rank_candidates_by_feature(
                    conn=conn,
                    user_feature=user_feature,
                    samples=samples,
                    max_candidates=max(1, min(cfg.feature_prefilter_limit, len(samples))),
                    get_gray_image_for_sample=glyph_sample_to_gray,
                )
            candidates: list[GlyphCandidate] = []
            try:
                for sample in samples:
                    sample_path, source_kind = _sample_to_png_path(sample)
                    if sample_path is None:
                        # Use a very low score metadata fallback so downstream report can still show weak evidence.
                        score = 5.0
                        method = "hybrid"
                        extras = {"score_reason": source_kind}
                    else:
                        try:
                            _, _, _, combined = combined_similarity(str(user_char_path), str(sample_path))
                            score = float(combined)
                            method = "cv_baseline"
                            extras = {"score_reason": source_kind}
                        finally:
                            sample_path.unlink(missing_ok=True)

                    canonical_author = normalize_author_name(conn, sample.author_name)
                    candidates.append(
                        GlyphCandidate(
                            author_name=canonical_author,
                            style=sample.style,
                            sample_id=str(sample.sample_id),
                            source="characters",
                            score=max(0.0, min(100.0, score)),
                            method=method,  # type: ignore[arg-type]
                            extras=extras,
                        )
                    )
            finally:
                user_char_path.unlink(missing_ok=True)

            candidates.sort(key=lambda x: x.score, reverse=True)
            ch.candidates = candidates[: cfg.top_k_per_char]
            if ch.candidates:
                matched_char_count += 1

            winning_author, winning_score, winning_weight = _pick_single_char_vote(
                ch.candidates, cfg.min_score_to_vote
            )
            if winning_author:
                stat = author_stats[winning_author]
                stat["weighted_score_sum"] += winning_score * winning_weight
                stat["confidence_sum"] += winning_weight
                stat["votes"] += 1
                stat["chars"].add(ch.char)

        bundle.authors = []
        for author_name, stat in author_stats.items():
            if stat["votes"] <= 0:
                continue
            confidence_sum = float(stat["confidence_sum"])
            if confidence_sum <= 0:
                continue
            avg = stat["weighted_score_sum"] / confidence_sum
            bundle.authors.append(
                AuthorAttribution(
                    author_name=author_name,
                    score=max(0.0, min(100.0, avg)),
                    votes=int(stat["votes"]),
                    evidence_chars=sorted(stat["chars"]),
                )
            )
        bundle.authors.sort(key=lambda x: (x.score, x.votes), reverse=True)
        bundle.authors = bundle.authors[: cfg.top_n_authors]
        bundle.meta.update(
            {
                "matcher_stats": {
                    "total_chars": total_char_count,
                    "cjk_chars": cjk_char_count,
                    "filtered_non_cjk_chars": filtered_non_cjk_chars,
                    "filtered_non_cjk_count": len(filtered_non_cjk_chars),
                    "db_covered_chars": db_covered_char_count,
                    "matched_chars_with_candidates": matched_char_count,
                    "db_coverage_ratio": round(
                        (db_covered_char_count / cjk_char_count), 4
                    )
                    if cjk_char_count
                    else 0.0,
                    "candidate_hit_ratio": round(
                        (matched_char_count / cjk_char_count), 4
                    )
                    if cjk_char_count
                    else 0.0,
                    "missing_in_db_chars": sorted(set(missing_in_db_chars)),
                    "author_vote_strategy": {
                        "type": "confidence_weighted_single_vote_per_char",
                        "min_score_to_vote": cfg.min_score_to_vote,
                        "confidence_weight": "quadratic((score-threshold)/(100-threshold))",
                        "author_dedup_per_char": True,
                    },
                }
            }
        )
    return bundle
