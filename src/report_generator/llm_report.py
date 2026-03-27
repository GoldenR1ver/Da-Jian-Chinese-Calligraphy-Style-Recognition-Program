"""LLM：旧版兼容与混合报告入口。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional, Union

from ..character_matcher.schema import MatchBundle
from .basic_report import generate_basic_report
from .complete_report import generate_complete_style_report
from .llm_client import chat_completion, parse_json_object
from .llm_config import resolve_openai_api_key, resolve_openai_base_url, resolve_openai_model
from .report_utils import with_meta
from .schema import StyleReport

PROMPT_VERSION = "style_report_zh_v1"
PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / f"{PROMPT_VERSION}.txt"


def _redact_bundle_dict(bundle: MatchBundle) -> dict[str, Any]:
    d = bundle.model_dump() if hasattr(bundle, "model_dump") else bundle.dict()
    if d.get("image_path"):
        p = str(d["image_path"])
        d["image_path"] = Path(p).name
    return d


def _load_prompt_template() -> str:
    if not PROMPT_PATH.is_file():
        raise FileNotFoundError(f"Prompt template missing: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8")


def generate_hybrid_llm_report(
    bundle: MatchBundle,
    *,
    radar_out: Optional[Union[Path, str]] = None,
    skip_radar: bool = False,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    timeout: float = 120.0,
) -> StyleReport:
    """
    混合报告：规则层 + 可选雷达图 + 基于八维与 Top5 的 LLM 评语。
    """
    return generate_complete_style_report(
        bundle,
        radar_out=radar_out,
        skip_radar=skip_radar,
        llm_commentary=True,
        openai_api_key=api_key,
        openai_base_url=base_url,
        openai_model=model,
    )


def generate_legacy_hybrid_prompt_report(
    bundle: MatchBundle,
    *,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    timeout: float = 120.0,
) -> StyleReport:
    """旧版「整包 match_bundle + rule_report」提示词（少用）。"""
    baseline = generate_basic_report(bundle)
    key = resolve_openai_api_key(api_key)
    if not key:
        return with_meta(
            baseline,
            {"llm_fallback_reason": "no_api_key", "prompt_version": PROMPT_VERSION},
        )

    url = resolve_openai_base_url(base_url)
    mdl = resolve_openai_model(model)

    payload = {
        "prompt_version": PROMPT_VERSION,
        "match_bundle": _redact_bundle_dict(bundle),
        "rule_report": baseline.model_dump() if hasattr(baseline, "model_dump") else baseline.dict(),
    }
    payload_json = json.dumps(payload, ensure_ascii=False, indent=2)
    template = _load_prompt_template()
    prompt = template.replace("{{INPUT_JSON}}", payload_json)

    try:
        raw = chat_completion(prompt, api_key=key, base_url=url, model=mdl, timeout=timeout)
        parsed = parse_json_object(raw)
    except Exception as e:
        return with_meta(
            baseline,
            {"llm_fallback_reason": f"llm_error: {e!s}", "prompt_version": PROMPT_VERSION},
        )

    summary = str(parsed.get("summary", "")).strip() or baseline.summary
    warnings_extra = parsed.get("warnings")
    if not isinstance(warnings_extra, list):
        warnings_extra = []
    narrative = parsed.get("narrative_zh")
    if narrative is not None and not isinstance(narrative, str):
        narrative = str(narrative)

    meta = dict(baseline.meta)
    meta["prompt_version"] = PROMPT_VERSION
    meta["llm"] = {
        "model": mdl,
        "base_url": url,
        "narrative_zh": narrative or "",
    }

    merged_warnings = list(baseline.warnings) + [str(w) for w in warnings_extra if str(w).strip()]

    return StyleReport(
        schema_version=baseline.schema_version,
        generator="hybrid",
        summary=summary,
        top_authors=baseline.top_authors,
        style_dimensions=baseline.style_dimensions,
        evidence=baseline.evidence,
        warnings=merged_warnings,
        meta=meta,
    )
