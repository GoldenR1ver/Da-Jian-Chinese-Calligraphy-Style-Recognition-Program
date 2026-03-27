"""完整报告：结构化结果 + 雷达图 + 可选 LLM 评语。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from ..character_matcher.schema import MatchBundle
from .basic_report import generate_basic_report
from .commentary_llm import attach_llm_commentary
from .radar_chart import render_eight_dim_radar
from .report_utils import with_meta
from .schema import StyleReport


def generate_complete_style_report(
    bundle: MatchBundle,
    *,
    radar_out: Optional[Union[Path, str]] = None,
    skip_radar: bool = False,
    llm_commentary: bool = False,
    openai_api_key: Optional[str] = None,
    openai_base_url: Optional[str] = None,
    openai_model: Optional[str] = None,
) -> StyleReport:
    """
    1. 规则层：Top5 书家、八维、证据。
    2. 可选：雷达图 PNG。
    3. 可选：基于八维 + Top5 的 LLM 评语（commentary_zh_v2）。
    """
    report = generate_basic_report(bundle)
    meta = report.meta or {}
    user_eight_en = meta.get("user_eight_dimensions_en") or {}

    if not skip_radar and radar_out and user_eight_en:
        try:
            p = render_eight_dim_radar(user_eight_en, Path(radar_out))
            components = dict((report.meta or {}).get("report_components") or {})
            components["eight_dim_radar_image"] = str(p)
            report = with_meta(
                report,
                {"radar_chart_path": str(p), "report_components": components},
            )
        except Exception as e:
            report = with_meta(report, {"radar_chart_error": str(e)})

    if llm_commentary:
        report = attach_llm_commentary(
            report,
            api_key=openai_api_key,
            base_url=openai_base_url,
            model=openai_model,
        )
    return report
