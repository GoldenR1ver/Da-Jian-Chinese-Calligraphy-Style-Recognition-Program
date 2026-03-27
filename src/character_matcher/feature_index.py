from __future__ import annotations

import json
import sqlite3
from typing import Optional

import cv2
import numpy as np

from .repository import GlyphSample


def render_svg_to_png(svg_text: str) -> Optional[bytes]:
    try:
        import cairosvg  # type: ignore
    except Exception:
        return None
    try:
        return cairosvg.svg2png(bytestring=svg_text.encode("utf-8"))
    except Exception:
        return None


def glyph_sample_to_gray(sample: GlyphSample) -> Optional[np.ndarray]:
    if sample.image_data:
        arr = np.frombuffer(sample.image_data, dtype=np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if sample.svg:
        png_bytes = render_svg_to_png(sample.svg)
        if png_bytes:
            arr = np.frombuffer(png_bytes, dtype=np.uint8)
            return cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    return None


def _normalize_image(gray: np.ndarray, target_size: tuple[int, int] = (64, 64)) -> np.ndarray:
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    h, w = binary.shape
    scale = min(target_size[0] / max(h, 1), target_size[1] / max(w, 1))
    nh = max(1, int(h * scale))
    nw = max(1, int(w * scale))
    resized = cv2.resize(binary, (nw, nh), interpolation=cv2.INTER_AREA)
    canvas = np.zeros(target_size, dtype=np.uint8)
    oy = (target_size[0] - nh) // 2
    ox = (target_size[1] - nw) // 2
    canvas[oy : oy + nh, ox : ox + nw] = resized
    return canvas


def extract_feature(gray: np.ndarray) -> np.ndarray:
    normalized = _normalize_image(gray)
    moments = cv2.moments(normalized)
    hu = cv2.HuMoments(moments).flatten()
    hu = np.sign(hu) * np.log10(np.abs(hu) + 1e-12)
    row_profile = normalized.sum(axis=1).astype(np.float32) / 255.0
    col_profile = normalized.sum(axis=0).astype(np.float32) / 255.0
    feat = np.concatenate([hu.astype(np.float32), row_profile, col_profile]).astype(np.float32)
    denom = np.linalg.norm(feat) + 1e-12
    return feat / denom


def ensure_feature_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS glyph_features (
            sample_id INTEGER PRIMARY KEY,
            feature_json TEXT NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_glyph_features_sample_id ON glyph_features(sample_id)")
    conn.commit()


def upsert_sample_feature(conn: sqlite3.Connection, sample_id: int, feature: np.ndarray) -> None:
    conn.execute(
        """
        INSERT INTO glyph_features (sample_id, feature_json)
        VALUES (?, ?)
        ON CONFLICT(sample_id) DO UPDATE SET
            feature_json=excluded.feature_json,
            updated_at=CURRENT_TIMESTAMP
        """,
        (sample_id, json.dumps(feature.tolist(), ensure_ascii=False)),
    )


def load_sample_feature(conn: sqlite3.Connection, sample_id: int) -> Optional[np.ndarray]:
    row = conn.execute(
        "SELECT feature_json FROM glyph_features WHERE sample_id = ?",
        (sample_id,),
    ).fetchone()
    if not row:
        return None
    arr = np.array(json.loads(row["feature_json"]), dtype=np.float32)
    denom = np.linalg.norm(arr) + 1e-12
    return arr / denom


def rank_candidates_by_feature(
    conn: sqlite3.Connection,
    user_feature: np.ndarray,
    samples: list[GlyphSample],
    max_candidates: int,
    get_gray_image_for_sample,
) -> list[GlyphSample]:
    ensure_feature_table(conn)
    scored: list[tuple[float, GlyphSample]] = []
    touched = False
    for sample in samples:
        feat = load_sample_feature(conn, sample.sample_id)
        if feat is None:
            gray = get_gray_image_for_sample(sample)
            if gray is None:
                continue
            feat = extract_feature(gray)
            upsert_sample_feature(conn, sample.sample_id, feat)
            touched = True
        score = float(np.dot(user_feature, feat))
        scored.append((score, sample))
    if touched:
        conn.commit()
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in scored[:max_candidates]]
