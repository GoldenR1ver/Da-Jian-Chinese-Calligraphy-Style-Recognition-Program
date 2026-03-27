"""从 MatchBundle 聚合书家相似度权重，计算用户八维书法向量。"""

from __future__ import annotations

from collections import defaultdict

import sqlite3

from ..character_matcher.repository import (
    EIGHT_DIMENSION_KEYS,
    db_connection,
    fetch_author_style_scores,
    normalize_author_name,
)
from ..character_matcher.schema import MatchBundle

EIGHT_DIMENSION_ZH: dict[str, str] = {
    "zhonghe": "中和",
    "duanzhuang": "端庄",
    "dianya": "典雅",
    "gupu": "古朴",
    "gangjin": "刚劲",
    "xianjun": "险峻",
    "satuo": "洒脱",
    "yanmei": "妍美",
}


def aggregate_author_weights(
    bundle: MatchBundle, conn: sqlite3.Connection | None = None
) -> dict[str, float]:
    """对所有逐字候选中的书家，按相似度分数累加作为权重（可选别名归一化）。"""
    w: dict[str, float] = defaultdict(float)
    for ch in bundle.chars:
        for c in ch.candidates:
            if not c.author_name:
                continue
            name = c.author_name
            if conn is not None:
                name = normalize_author_name(conn, name) or name
            w[name] += max(0.0, float(c.score))
    return dict(w)


def top_n_calligraphers(weights: dict[str, float], n: int = 5) -> list[str]:
    if not weights:
        return []
    items = sorted(weights.items(), key=lambda x: (-x[1], x[0]))
    return [name for name, _ in items[:n]]


def normalize_author_eight_dimensions(author_row: dict) -> dict[str, float]:
    """
    对单个书家的八维分数做作家内归一化（min-max 到 0–100），突出个人风格差异。
    """
    vals = [float(author_row[k]) for k in EIGHT_DIMENSION_KEYS]
    vmin = min(vals)
    vmax = max(vals)
    span = vmax - vmin
    if span <= 1e-9:
        # Flat profile: keep neutral midpoint to avoid amplifying noise.
        return {k: 50.0 for k in EIGHT_DIMENSION_KEYS}
    return {
        k: ((float(author_row[k]) - vmin) / span) * 100.0
        for k in EIGHT_DIMENSION_KEYS
    }


def weighted_user_eight_dimensions(
    conn: sqlite3.Connection,
    weights: dict[str, float],
) -> dict[str, float]:
    """
    对「在 author_style_scores 中八维齐全」的书家，用相似度累加权重做加权平均，得到八维（0–100）。
    """
    numer = {k: 0.0 for k in EIGHT_DIMENSION_KEYS}
    denom = 0.0
    for author, wt in weights.items():
        if wt <= 0:
            continue
        row = fetch_author_style_scores(conn, author)
        if not row:
            continue
        vals: list[float] = []
        for k in EIGHT_DIMENSION_KEYS:
            v = row.get(k)
            if not isinstance(v, (int, float)):
                vals = []
                break
            vals.append(float(v))
        if len(vals) != len(EIGHT_DIMENSION_KEYS):
            continue
        normalized_row = normalize_author_eight_dimensions(
            {k: v for k, v in zip(EIGHT_DIMENSION_KEYS, vals)}
        )
        denom += wt
        for k in EIGHT_DIMENSION_KEYS:
            val = normalized_row[k]
            numer[k] += val * wt
    if denom <= 0:
        return {}
    return {k: numer[k] / denom for k in EIGHT_DIMENSION_KEYS}


def user_eight_dimensions_zh(user_eight: dict[str, float]) -> dict[str, float]:
    """转为中文维度名 -> 数值，供展示与 LLM。"""
    return {EIGHT_DIMENSION_ZH[k]: user_eight[k] for k in EIGHT_DIMENSION_KEYS if k in user_eight}
