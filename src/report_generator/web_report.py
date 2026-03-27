"""Render StyleReport into a readable standalone HTML page."""

from __future__ import annotations

import base64
import html
import mimetypes
from pathlib import Path
from typing import Any

from .report_utils import style_report_dump
from .schema import StyleReport


def _esc(v: Any) -> str:
    return html.escape(str(v), quote=True)


def _render_list(items: list[str]) -> str:
    if not items:
        return "<p class='muted'>暂无</p>"
    return "<ul>" + "".join(f"<li>{_esc(x)}</li>" for x in items) + "</ul>"


def _render_table(rows: list[dict], columns: list[tuple[str, str]]) -> str:
    if not rows:
        return "<p class='muted'>暂无</p>"
    head = "".join(f"<th>{_esc(title)}</th>" for _, title in columns)
    body_rows = []
    for r in rows:
        tds = "".join(f"<td>{_esc(r.get(key, ''))}</td>" for key, _ in columns)
        body_rows.append(f"<tr>{tds}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"


def _embed_image_src(path_like: Any) -> str:
    """Convert local image file to data URI for standalone HTML."""
    if not path_like:
        return ""
    try:
        path = Path(str(path_like)).expanduser().resolve()
        if not path.is_file():
            return ""
        content = path.read_bytes()
        if not content:
            return ""
        mime, _ = mimetypes.guess_type(str(path))
        mime = mime or "image/png"
        b64 = base64.b64encode(content).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except Exception:
        return ""


def render_style_report_html(report: StyleReport, out_path: Path) -> Path:
    d = style_report_dump(report)
    meta = dict(d.get("meta") or {})
    components = dict(meta.get("report_components") or {})

    top5 = list(components.get("top5_similar_calligraphers") or d.get("top_authors") or [])
    char_top1 = list(components.get("single_char_top1") or [])
    style_commentary = str(components.get("style_overall_commentary") or "").strip()
    recommendations = list(components.get("similar_calligrapher_recommendations") or [])
    radar_path = components.get("eight_dim_radar_image") or meta.get("radar_chart_path")
    input_image_path = components.get("input_image_path") or meta.get("input_image_path")

    llm_meta = dict(meta.get("llm_commentary") or {})
    llm_commentary = str(llm_meta.get("commentary_zh") or "").strip()
    llm_model = str(llm_meta.get("model") or "").strip()
    llm_block = (
        f"<p>{_esc(llm_commentary)}</p><p class='muted'>模型：{_esc(llm_model or '未标注')}</p>"
        if llm_commentary
        else "<p class='muted'>当前未启用 LLM 扩展评语（预留区块，可后续开启）。</p>"
    )

    eight_dims_zh = dict(meta.get("user_eight_dimensions_zh") or {})
    eight_dim_rows = [{"dimension": k, "score": round(float(v), 3)} for k, v in eight_dims_zh.items()]

    radar_src = _embed_image_src(radar_path)
    radar_html = (
        f"<img src='{_esc(radar_src)}' alt='书法八维雷达图' class='radar' />"
        if radar_src
        else "<p class='muted'>未生成雷达图或雷达图文件不存在</p>"
    )
    input_image_src = _embed_image_src(input_image_path)
    input_image_html = (
        f"<img src='{_esc(input_image_src)}' alt='用户原始图片' class='radar' />"
        if input_image_src
        else "<p class='muted'>未记录输入原图路径或原图文件不存在</p>"
    )

    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>书法风格分析报告</title>
  <style>
    body {{ font-family: "Microsoft YaHei", "PingFang SC", sans-serif; margin: 24px auto; max-width: 1080px; line-height: 1.6; color: #222; padding: 0 12px; }}
    h1, h2 {{ margin: 0 0 12px; }}
    .muted {{ color: #666; }}
    .card {{ border: 1px solid #e5e7eb; border-radius: 10px; padding: 14px 16px; margin: 12px 0; background: #fff; }}
    table {{ width: 100%; border-collapse: collapse; margin: 8px 0; }}
    th, td {{ border: 1px solid #e5e7eb; padding: 8px; text-align: left; font-size: 14px; }}
    th {{ background: #f8fafc; }}
    .radar {{ max-width: 520px; width: 100%; border: 1px solid #eee; border-radius: 8px; }}
    .section-title {{ color: #111827; }}
    code {{ background: #f3f4f6; padding: 2px 4px; border-radius: 4px; }}
  </style>
</head>
<body>
  <h1>书法风格分析报告</h1>
  <p class="muted">生成器：{_esc(d.get("generator", "rule_based"))} | Schema：{_esc(d.get("schema_version", "0.1.0"))}</p>

  <div class="card">
    <h2 class="section-title">总体摘要</h2>
    <p>{_esc(d.get("summary", ""))}</p>
  </div>

  <div class="card">
    <h2 class="section-title">1. 用户原始图片</h2>
    {input_image_html}
  </div>

  <div class="card">
    <h2 class="section-title">2. 书法八维图片</h2>
    {radar_html}
  </div>

  <div class="card">
    <h2 class="section-title">3. 总体最相似书法家 TOP 5</h2>
    {_render_list(top5)}
  </div>

  <div class="card">
    <h2 class="section-title">4. 单字最相似书法家 TOP 1</h2>
    {_render_table(char_top1, [("char", "单字"), ("author_name", "最相似书家"), ("score", "相似度"), ("style", "书体")])}
  </div>

  <div class="card">
    <h2 class="section-title">5. 当前书法风格总评（规则版）</h2>
    <p>{_esc(style_commentary or "暂无规则总评。")}</p>
  </div>

  <div class="card">
    <h2 class="section-title">6. 基于当前风格的相似书法家推荐</h2>
    {_render_table(recommendations, [("author_name", "书家"), ("similarity_weight", "权重"), ("reason", "推荐理由")])}
  </div>

  <div class="card">
    <h2 class="section-title">八维分数明细</h2>
    {_render_table(eight_dim_rows, [("dimension", "维度"), ("score", "分数")])}
  </div>

  <div class="card">
    <h2 class="section-title">LLM 扩展分析（可选）</h2>
    {llm_block}
  </div>

  <div class="card">
    <h2 class="section-title">告警与说明</h2>
    {_render_list(list(d.get("warnings") or []))}
  </div>
</body>
</html>
"""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_text, encoding="utf-8")
    return out_path.resolve()

