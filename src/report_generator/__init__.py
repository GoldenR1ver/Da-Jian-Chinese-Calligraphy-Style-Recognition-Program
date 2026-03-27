"""Report generation (structured + radar + optional LLM)."""

from .basic_report import generate_basic_report
from .commentary_llm import attach_llm_commentary
from .complete_report import generate_complete_style_report
from .llm_report import generate_hybrid_llm_report, generate_legacy_hybrid_prompt_report
from .schema import StyleReport
from .web_report import render_style_report_html

__all__ = [
    "StyleReport",
    "generate_basic_report",
    "generate_complete_style_report",
    "render_style_report_html",
    "attach_llm_commentary",
    "generate_hybrid_llm_report",
    "generate_legacy_hybrid_prompt_report",
]
