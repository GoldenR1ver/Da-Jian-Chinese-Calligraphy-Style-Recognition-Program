"""根据书法八维与 Top5 书家生成 LLM 文字评语。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .llm_config import resolve_openai_api_key, resolve_openai_base_url, resolve_openai_model
from .llm_client import chat_completion, parse_json_object
from .report_utils import style_report_dump, style_report_from_dict, with_meta
from .schema import StyleReport

COMMENTARY_PROMPT_VERSION = "commentary_zh_v2"
COMMENTARY_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / f"{COMMENTARY_PROMPT_VERSION}.txt"


def _fill_commentary_prompt(payload: dict[str, Any]) -> str:
    template = COMMENTARY_PROMPT_PATH.read_text(encoding="utf-8")
    blob = json.dumps(payload, ensure_ascii=False, indent=2)
    if "{{INPUT_JSON}}" not in template:
        raise ValueError("commentary prompt must contain {{INPUT_JSON}}")
    return template.replace("{{INPUT_JSON}}", blob)


def attach_llm_commentary(
    report: StyleReport,
    *,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    timeout: float = 120.0,
) -> StyleReport:
    """在已有 StyleReport（含 meta 中八维与 Top5）上附加 LLM 评语。"""
    key = resolve_openai_api_key(api_key)
    if not key:
        return with_meta(
            report,
            {
                "commentary_llm_fallback": "no_api_key",
                "commentary_prompt_version": COMMENTARY_PROMPT_VERSION,
            },
        )

    url = resolve_openai_base_url(base_url)
    mdl = resolve_openai_model(model)
    d = style_report_dump(report)
    meta = dict(d.get("meta") or {})
    payload = {
        "prompt_version": COMMENTARY_PROMPT_VERSION,
        "top_five_calligraphers": meta.get("top_five_calligraphers", report.top_authors),
        "user_eight_dimensions": meta.get("user_eight_dimensions_zh")
        or meta.get("user_eight_dimensions")
        or meta.get("user_six_dimensions_zh"),
        "radar_chart_path": meta.get("radar_chart_path"),
        "author_similarity_weights": meta.get("author_similarity_weights"),
    }
    prompt = _fill_commentary_prompt(payload)

    try:
        raw = chat_completion(prompt, api_key=key, base_url=url, model=mdl, timeout=timeout)
        parsed = parse_json_object(raw)
    except Exception as e:
        return with_meta(
            report,
            {
                "commentary_llm_fallback": f"llm_error: {e!s}",
                "commentary_prompt_version": COMMENTARY_PROMPT_VERSION,
            },
        )

    summary = str(parsed.get("summary", "")).strip() or report.summary
    commentary = str(parsed.get("commentary_zh", "")).strip()

    meta = dict(meta)
    meta["commentary_prompt_version"] = COMMENTARY_PROMPT_VERSION
    meta["llm_commentary"] = {
        "model": mdl,
        "base_url": url,
        "commentary_zh": commentary,
    }

    d["summary"] = summary
    d["generator"] = "hybrid"
    d["meta"] = meta
    return style_report_from_dict(d)
