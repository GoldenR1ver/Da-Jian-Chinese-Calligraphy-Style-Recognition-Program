from __future__ import annotations

from .schema import ReportEvidenceItem, ReportStyleDimension, StyleReport
from .rule_commentary import (
    build_rule_based_overall_commentary,
    build_similar_calligrapher_recommendations,
)
from .style_math import (
    EIGHT_DIMENSION_ZH,
    aggregate_author_weights,
    normalize_author_eight_dimensions,
    top_n_calligraphers,
    user_eight_dimensions_zh,
    weighted_user_eight_dimensions,
)
from ..character_matcher.repository import EIGHT_DIMENSION_KEYS, db_connection, fetch_author_style_scores
from ..character_matcher.schema import MatchBundle


def _build_style_dimensions_from_eight(user_eight: dict[str, float]) -> list[ReportStyleDimension]:
    """八维列表：weight 用 0–1 表示相对强度（相对最大维）。"""
    if not user_eight:
        return []
    max_v = max(user_eight.values()) if user_eight.values() else 1.0
    max_v = max(max_v, 1e-6)
    out: list[ReportStyleDimension] = []
    for k in EIGHT_DIMENSION_KEYS:
        v = float(user_eight.get(k, 0.0))
        out.append(
            ReportStyleDimension(
                name=EIGHT_DIMENSION_ZH[k],
                weight=max(0.0, min(1.0, v / max_v)),
                evidence=[f"weighted_score={v:.1f}"],
            )
        )
    return out


def generate_basic_report(bundle: MatchBundle, top_n: int = 5) -> StyleReport:
    """
    1) 列举最接近的 top_n 位书法家（默认 5）：按所有候选中相似度累加排序。
    2) 书法八维：对「在评分表中有完整八维」的书家，以相似度累加为权重加权平均。
    """
    with db_connection() as conn:
        # 统一别名到 canonical 名称，避免作者名和作品名被拆分统计。
        weights = aggregate_author_weights(bundle, conn=conn)
        top_five = top_n_calligraphers(weights, n=top_n)
        user_eight_en = weighted_user_eight_dimensions(conn, weights)
        author_top_dimensions_zh: dict[str, str] = {}
        for author in top_five:
            row = fetch_author_style_scores(conn, author)
            if not row:
                continue
            vals_ok = all(isinstance(row.get(k), (int, float)) for k in EIGHT_DIMENSION_KEYS)
            if not vals_ok:
                continue
            normalized = normalize_author_eight_dimensions({k: float(row[k]) for k in EIGHT_DIMENSION_KEYS})
            top_key = max(normalized.items(), key=lambda kv: kv[1])[0]
            author_top_dimensions_zh[author] = EIGHT_DIMENSION_ZH[top_key]

    evidence: list[ReportEvidenceItem] = []
    for ch in bundle.chars:
        if not ch.candidates:
            continue
        best = max(ch.candidates, key=lambda c: c.score)
        evidence.append(
            ReportEvidenceItem(
                char=ch.char,
                author_name=best.author_name,
                score=best.score,
                why=[f"best_candidate_by_score(method={best.method})"],
                extras={
                    "style": best.style,
                    "dynasty": best.dynasty,
                    "source": best.source,
                },
            )
        )

    user_eight_zh = user_eight_dimensions_zh(user_eight_en) if user_eight_en else {}
    style_overall_commentary = build_rule_based_overall_commentary(user_eight_en)
    user_dominant_dim_zh = None
    if user_eight_en:
        user_dominant_key = max(user_eight_en.items(), key=lambda kv: kv[1])[0]
        user_dominant_dim_zh = EIGHT_DIMENSION_ZH[user_dominant_key]
    similar_calligrapher_recommendations = build_similar_calligrapher_recommendations(
        top_authors=top_five,
        author_weights=weights,
        author_top_dimensions_zh=author_top_dimensions_zh,
        user_dominant_dimension_zh=user_dominant_dim_zh,
    )
    char_top1 = [
        {
            "char": item.char,
            "author_name": item.author_name,
            "score": round(float(item.score), 3),
            "style": item.extras.get("style") if item.extras else None,
        }
        for item in evidence
    ]

    matcher_stats = (bundle.meta or {}).get("matcher_stats", {})
    warnings: list[str] = []
    filtered_non_cjk = matcher_stats.get("filtered_non_cjk_chars") or []
    missing_in_db = matcher_stats.get("missing_in_db_chars") or []
    cjk_chars = int(matcher_stats.get("cjk_chars") or 0)
    db_covered = int(matcher_stats.get("db_covered_chars") or 0)
    matched_chars = int(matcher_stats.get("matched_chars_with_candidates") or 0)
    db_cov_ratio = float(matcher_stats.get("db_coverage_ratio") or 0.0)

    if filtered_non_cjk:
        warnings.append(
            f"已过滤 {len(filtered_non_cjk)} 个非中文字符：{''.join(filtered_non_cjk[:20])}"
        )
    if missing_in_db:
        preview = "、".join(missing_in_db[:15])
        more = " 等" if len(missing_in_db) > 15 else ""
        warnings.append(
            f"字库缺少 {len(missing_in_db)} 个识别字符样本：{preview}{more}。"
        )
    if cjk_chars > 0:
        warnings.append(
            f"匹配覆盖率：字库覆盖 {db_covered}/{cjk_chars} ({db_cov_ratio:.1%})，产出候选 {matched_chars}/{cjk_chars}。"
        )

    if top_five:
        summary = (
            f"与您作品最接近的五位书法家（按相似度累加排序）为：{'、'.join(top_five)}。"
        )
    else:
        summary = "未从字库匹配到足够候选，暂无法列出最接近的书家。"
    if not evidence:
        summary += "（当前缺少可用的逐字匹配证据）"
    if user_eight_zh:
        summary += (
            " 根据匹配书家加权（作家内八维归一化后），您的书法八维（中和、端庄、典雅、古朴、刚劲、险峻、洒脱、妍美）已估算，"
            "详见报告 meta 与雷达图。"
        )
    if style_overall_commentary:
        summary += f" 总评：{style_overall_commentary}"

    return StyleReport(
        generator="rule_based",
        summary=summary,
        top_authors=top_five,
        style_dimensions=_build_style_dimensions_from_eight(user_eight_en),
        evidence=evidence[:50],
        warnings=warnings,
        meta={
            "bundle_version": bundle.version,
            "ocr_engine": bundle.ocr_engine,
            "input_image_path": bundle.image_path,
            "top_five_calligraphers": top_five,
            "author_similarity_weights": weights,
            "user_eight_dimensions_zh": user_eight_zh,
            "user_eight_dimensions_en": user_eight_en,
            "eight_dim_normalization": {
                "enabled": True,
                "method": "per_author_minmax_0_100_then_weighted_average",
            },
            "coverage": {
                "cjk_chars": cjk_chars,
                "db_covered_chars": db_covered,
                "matched_chars_with_candidates": matched_chars,
                "db_coverage_ratio": db_cov_ratio,
                "candidate_hit_ratio": float(matcher_stats.get("candidate_hit_ratio") or 0.0),
            },
            "matcher_stats": matcher_stats,
            "report_components": {
                "eight_dim_radar_image": None,  # Filled by complete_report when radar is rendered.
                "input_image_path": bundle.image_path,
                "top5_similar_calligraphers": top_five,
                "single_char_top1": char_top1,
                "style_overall_commentary": style_overall_commentary,
                "similar_calligrapher_recommendations": similar_calligrapher_recommendations,
            },
        },
    )
