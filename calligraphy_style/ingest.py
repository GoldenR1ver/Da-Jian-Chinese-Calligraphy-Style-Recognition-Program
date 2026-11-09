"""固定的作品导入流程：切字、对齐、清洗、入库。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import sqlite3

from . import db, images, ocr


@dataclass
class ImportedGlyph:
    order: int
    form: str
    canonical: str
    bbox: tuple[int, int, int, int]


@dataclass
class ImportResult:
    work_id: int
    author: str
    style: str
    label_source: str
    glyphs: list[ImportedGlyph]


def _labels_for_segments(
    image_path: Path,
    segments: list[images.Segment],
    text: Optional[str],
    use_baidu: bool,
    api_key: Optional[str],
    secret_key: Optional[str],
) -> tuple[list[str], str]:
    if text and text.strip():
        chars = images.cjk_chars(text)
        source = "text"
    elif use_baidu:
        recognized = ocr.recognize_baidu(image_path, api_key, secret_key)
        chars_or_none = ocr.labels_from_ocr([seg.bbox for seg in segments], recognized)
        missing = [i for i, ch in enumerate(chars_or_none) if not ch or not images.is_cjk(ch)]
        if missing:
            raise RuntimeError(
                f"百度 OCR 有 {len(missing)} 个切块对不上汉字（序号 {missing[:12]}）。"
                "可改用 --text 手工释文。"
            )
        chars = [ch for ch in chars_or_none if ch]
        source = "baidu"
    else:
        raise RuntimeError("导入时需要 --text 释文，或加上 --ocr baidu")

    if len(chars) != len(segments):
        raise RuntimeError(
            f"切出 {len(segments)} 个字块，释文有 {len(chars)} 个汉字。"
            "请改 --layout（horizontal 横写从左到右，vertical 竖写从右到左），"
            "或用 --debug-dir 查看切分。"
        )
    return chars, source


def import_work(
    conn: sqlite3.Connection,
    image_path: Path,
    author: str,
    style: str,
    *,
    title: Optional[str] = None,
    text: Optional[str] = None,
    use_baidu: bool = False,
    layout: str = "horizontal",
    api_key: Optional[str] = None,
    secret_key: Optional[str] = None,
    debug_dir: Optional[Path] = None,
) -> ImportResult:
    if layout not in {"horizontal", "vertical"}:
        raise ValueError("layout 只能是 horizontal 或 vertical")
    image_path = image_path.expanduser().resolve()
    _, segments = images.split_page(image_path, layout)
    if not segments:
        raise RuntimeError("没有切出单字。请确认图片是浅底深字，并且字与字之间有间隔。")

    try:
        labels, label_source = _labels_for_segments(
            image_path, segments, text, use_baidu, api_key, secret_key
        )
    except Exception:
        if debug_dir:
            images.write_debug(segments, [None] * len(segments), debug_dir)
        raise
    if debug_dir:
        images.write_debug(segments, labels, debug_dir)

    author_name = db.resolve_author_name(conn, author)
    style_id = db.ensure_author_style(conn, author_name, style)
    cur = conn.execute(
        """
        INSERT INTO works(author_style_id, title, source_path, layout, label_source)
        VALUES (?, ?, ?, ?, ?)
        """,
        (style_id, title, str(image_path), layout, label_source),
    )
    work_id = int(cur.lastrowid)
    imported: list[ImportedGlyph] = []
    for order, (segment, form) in enumerate(zip(segments, labels)):
        character_id, variant_id, canonical = db.resolve_form(conn, form)
        x, y, w, h = segment.bbox
        conn.execute(
            """
            INSERT INTO glyphs(
                work_id, character_id, variant_id, author_style_id, image,
                bbox_x, bbox_y, bbox_w, bbox_h, reading_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (work_id, character_id, variant_id, style_id, segment.png, x, y, w, h, order),
        )
        imported.append(ImportedGlyph(order=order, form=form, canonical=canonical, bbox=segment.bbox))
    conn.commit()
    return ImportResult(
        work_id=work_id,
        author=author_name,
        style=style.strip(),
        label_source=label_source,
        glyphs=imported,
    )
