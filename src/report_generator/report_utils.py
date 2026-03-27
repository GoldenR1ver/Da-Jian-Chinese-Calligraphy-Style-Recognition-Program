from __future__ import annotations

from typing import Any

from .schema import StyleReport


def style_report_dump(r: StyleReport) -> dict[str, Any]:
    return r.model_dump() if hasattr(r, "model_dump") else r.dict()


def style_report_from_dict(d: dict[str, Any]) -> StyleReport:
    return StyleReport.model_validate(d) if hasattr(StyleReport, "model_validate") else StyleReport(**d)


def with_meta(base: StyleReport, meta_updates: dict[str, Any]) -> StyleReport:
    d = style_report_dump(base)
    m = dict(d.get("meta") or {})
    m.update(meta_updates)
    d["meta"] = m
    return style_report_from_dict(d)
