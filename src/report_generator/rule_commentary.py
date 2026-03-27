"""Rule-based style commentary and recommendation helpers."""

from __future__ import annotations

from typing import Optional

from .style_math import EIGHT_DIMENSION_ZH

# User-provided expression pool for each dimension.
DIMENSION_PHRASES: dict[str, tuple[str, str, str]] = {
    "zhonghe": ("技巧丰富", "情感恬淡", "内容全面"),
    "duanzhuang": ("大气端庄", "温润自然", "结体严密"),
    "dianya": ("清新典雅", "君子藏器", "笔画丰满"),
    "gupu": ("古雅浑朴", "纯粹拙厚", "简练质朴"),
    "yanmei": ("婉丽秀美", "婀娜多姿", "空灵疏淡"),
    "gangjin": ("斩钉截铁", "恢宏大气", "简静雄强"),
    "xianjun": ("用笔弄险", "技巧突出", "风格强烈"),
    "satuo": ("奔放夸张", "真气弥漫", "豪放不羁"),
}


def _intensity_bucket(score: float) -> str:
    if score >= 70:
        return "high"
    if score >= 40:
        return "mid"
    return "low"


def _sentence_for_dimension(dim_key: str, score: float) -> str:
    name = EIGHT_DIMENSION_ZH[dim_key]
    a, b, c = DIMENSION_PHRASES[dim_key]
    level = _intensity_bucket(float(score))
    if level == "high":
        return f"{name}特征较为鲜明，{a}，{b}，{c}。"
    if level == "mid":
        return f"{name}表现较为稳定，呈现出{a}、{b}的倾向。"
    return f"{name}表达相对含蓄，仍可见{a}与{b}的基础。"


def build_rule_based_overall_commentary(user_eight_en: dict[str, float]) -> str:
    """Build overall commentary from top dimensions, without LLM."""
    if not user_eight_en:
        return "当前有效风格证据较少，建议增加字数或提高图像质量后再进行分析。"
    ordered = sorted(user_eight_en.items(), key=lambda kv: kv[1], reverse=True)
    top_dims = [k for k, _ in ordered[:3]]
    weakest_key, weakest_val = ordered[-1]

    parts = [_sentence_for_dimension(k, float(user_eight_en.get(k, 0.0))) for k in top_dims]
    weak_name = EIGHT_DIMENSION_ZH[weakest_key]
    weak_level = _intensity_bucket(float(weakest_val))
    if weak_level == "low":
        parts.append(f"相较之下，{weak_name}维度暂不突出，可在后续创作中有意识强化。")
    return "".join(parts)


def build_similar_calligrapher_recommendations(
    *,
    top_authors: list[str],
    author_weights: dict[str, float],
    author_top_dimensions_zh: dict[str, str],
    user_dominant_dimension_zh: Optional[str],
) -> list[dict]:
    """Build recommendation cards from matched authors."""
    out: list[dict] = []
    for name in top_authors:
        if not name:
            continue
        dim_zh = author_top_dimensions_zh.get(name)
        if dim_zh and user_dominant_dimension_zh and dim_zh == user_dominant_dimension_zh:
            reason = f"与当前作品同样偏重“{dim_zh}”，风格契合度较高。"
        elif dim_zh:
            reason = f"在“{dim_zh}”维度较突出，可作为风格对照与临摹参考。"
        else:
            reason = "整体相似度较高，可作为临摹与风格比较参考。"
        out.append(
            {
                "author_name": name,
                "similarity_weight": round(float(author_weights.get(name, 0.0)), 3),
                "reason": reason,
            }
        )
    return out

