"""用字库样本给一张新作品做书家与八维估计。"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import sqlite3
from skimage.metrics import structural_similarity as ssim

from . import db, images, ocr
from .seed import DIMENSIONS

MIN_VOTE = 45.0
SAMPLE_LIMIT = 80
PREFILTER = 30


def _normalize_ink(gray: np.ndarray) -> np.ndarray:
    blur = cv2.medianBlur(gray, 3)
    _, mask = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return mask


def _feature(gray: np.ndarray) -> np.ndarray:
    ink = _normalize_ink(gray)
    moments = cv2.moments(ink)
    hu = cv2.HuMoments(moments).flatten()
    hu = np.sign(hu) * np.log10(np.abs(hu) + 1e-12)
    row_profile = ink.sum(axis=1).astype(np.float32) / 255.0
    col_profile = ink.sum(axis=0).astype(np.float32) / 255.0
    feat = np.concatenate([hu.astype(np.float32), row_profile, col_profile])
    return feat / (np.linalg.norm(feat) + 1e-12)


def _similarity(left: np.ndarray, right: np.ndarray) -> float:
    a = _normalize_ink(left)
    b = _normalize_ink(right)
    sift_score = 0.0
    if hasattr(cv2, "SIFT_create"):
        try:
            sift = cv2.SIFT_create()
            kp1, des1 = sift.detectAndCompute(a, None)
            kp2, des2 = sift.detectAndCompute(b, None)
            if des1 is not None and des2 is not None and len(kp1) and len(kp2):
                matcher = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
                pairs = matcher.knnMatch(des1, des2, k=2)
                good = []
                for pair in pairs:
                    if len(pair) == 1:
                        good.append(pair[0])
                        continue
                    first, second = pair[0], pair[1]
                    if first.distance < 0.7 * second.distance:
                        good.append(first)
                sift_score = min(100.0, 100.0 * len(good) / min(len(kp1), len(kp2)))
        except cv2.error:
            sift_score = 0.0
    template = cv2.matchTemplate(a, b, cv2.TM_CCOEFF_NORMED)
    template_score = float(np.clip(template.max() * 100.0, 0, 100))
    struct = float(ssim(a, b, data_range=255))
    struct_score = float(np.clip(struct * 100.0, 0, 100))
    if sift_score <= 0:
        return float(np.clip(0.45 * template_score + 0.55 * struct_score, 0, 100))
    return float(np.clip(0.3 * sift_score + 0.3 * template_score + 0.4 * struct_score, 0, 100))


def _confidence(score: float) -> float:
    if score < MIN_VOTE:
        return 0.0
    span = max(1e-6, 100.0 - MIN_VOTE)
    normalized = max(0.0, min(1.0, (score - MIN_VOTE) / span))
    return normalized * normalized


def _labels(image_path: Path, segments: list[images.Segment], text: Optional[str], use_baidu: bool) -> list[str]:
    if text and text.strip():
        chars = images.cjk_chars(text)
    elif use_baidu:
        recognized = ocr.recognize_baidu(image_path)
        chars_or_none = ocr.labels_from_ocr([seg.bbox for seg in segments], recognized)
        if any(ch is None or not images.is_cjk(ch) for ch in chars_or_none):
            raise RuntimeError("OCR 结果无法和切块对齐，请改用 --text")
        chars = [ch for ch in chars_or_none if ch]
    else:
        raise RuntimeError("比对时需要 --text，或加上 --ocr baidu")
    if len(chars) != len(segments):
        raise RuntimeError(f"切出 {len(segments)} 个字块，释文有 {len(chars)} 个汉字")
    return chars


def _eight_dimensions(conn: sqlite3.Connection, weights: dict[int, float]) -> dict[str, float]:
    keys = [key for key, _ in DIMENSIONS]
    numer = {key: 0.0 for key in keys}
    denom = 0.0
    for style_id, weight in weights.items():
        if weight <= 0:
            continue
        row = db.fetch_style_score(conn, style_id)
        if not row:
            continue
        values = [float(row[key]) for key in keys]
        denom += weight
        for key, value in zip(keys, values):
            numer[key] += value * weight
    if denom <= 0:
        return {}
    return {key: numer[key] / denom for key in keys}


def analyze_image(
    conn: sqlite3.Connection,
    image_path: Path,
    *,
    text: Optional[str] = None,
    use_baidu: bool = False,
    layout: str = "horizontal",
) -> dict:
    image_path = image_path.expanduser().resolve()
    _, segments = images.split_page(image_path, layout)
    if not segments:
        raise RuntimeError("没有切出单字")
    labels = _labels(image_path, segments, text, use_baidu)

    per_char = []
    votes: dict[tuple[str, str, int], dict] = defaultdict(
        lambda: {"score_sum": 0.0, "weight_sum": 0.0, "votes": 0, "chars": []}
    )
    weight_by_style: dict[int, float] = defaultdict(float)

    for segment, form in zip(segments, labels):
        found = db.lookup_form(conn, form)
        canonical = found[2] if found else form
        rows = list(db.iter_glyphs_for_canonical(conn, canonical))[:SAMPLE_LIMIT] if found else []
        query_feat = _feature(segment.gray)
        ranked: list[tuple[float, sqlite3.Row, np.ndarray]] = []
        for row in rows:
            sample = images.decode_png(row["image"])
            feat = _feature(sample)
            ranked.append((float(np.dot(query_feat, feat)), row, sample))
        ranked.sort(key=lambda item: item[0], reverse=True)
        scored = []
        for _, row, sample in ranked[:PREFILTER]:
            score = _similarity(segment.gray, sample)
            scored.append(
                {
                    "author": row["author_name"],
                    "style": row["style_name"],
                    "author_style_id": int(row["author_style_id"]),
                    "form": row["form"],
                    "score": round(score, 2),
                }
            )
        scored.sort(key=lambda item: item["score"], reverse=True)
        top = scored[:5]
        per_char.append(
            {
                "form": form,
                "canonical": canonical,
                "candidates": top,
                "in_database": bool(rows),
            }
        )
        best_by_author: dict[tuple[str, str, int], dict] = {}
        for item in top:
            if item["score"] < MIN_VOTE:
                continue
            key = (item["author"], item["style"], item["author_style_id"])
            prev = best_by_author.get(key)
            if prev is None or item["score"] > prev["score"]:
                best_by_author[key] = item
        winner = None
        winner_value = -1.0
        for key, item in best_by_author.items():
            weight = _confidence(item["score"])
            value = item["score"] * weight
            if value > winner_value:
                winner = (key, item, weight)
                winner_value = value
        if winner:
            key, item, weight = winner
            bucket = votes[key]
            bucket["score_sum"] += item["score"] * weight
            bucket["weight_sum"] += weight
            bucket["votes"] += 1
            bucket["chars"].append(form)
            weight_by_style[key[2]] += item["score"]

    authors = []
    for (author, style, style_id), bucket in votes.items():
        if bucket["weight_sum"] <= 0:
            continue
        authors.append(
            {
                "author": author,
                "style": style,
                "author_style_id": style_id,
                "score": round(bucket["score_sum"] / bucket["weight_sum"], 2),
                "votes": bucket["votes"],
                "chars": bucket["chars"],
            }
        )
    authors.sort(key=lambda item: (item["score"], item["votes"]), reverse=True)
    eight = _eight_dimensions(conn, weight_by_style)
    names = dict(DIMENSIONS)
    eight_zh = {names[key]: round(value, 1) for key, value in eight.items()}
    if authors:
        head = "、".join(f"{item['author']}（{item['style']}）" for item in authors[:3])
        summary = f"这幅字目前更接近：{head}。"
    else:
        summary = "字库里还没有足够接近的样本。请先导入同一类书家的单字作品。"
    if eight_zh:
        dominant = max(eight_zh.items(), key=lambda item: item[1])[0]
        summary += f"按已有风格评分加权，突出的一维是「{dominant}」。"
    return {
        "image": str(image_path),
        "layout": layout,
        "glyphs": per_char,
        "authors": authors[:5],
        "eight_dimensions": eight_zh,
        "summary": summary,
    }
