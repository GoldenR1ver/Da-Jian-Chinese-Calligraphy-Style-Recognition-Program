"""可选的百度高精度 OCR，只负责给已经切好的字块贴标签。"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class OcrChar:
    char: str
    bbox: tuple[int, int, int, int]


def recognize_baidu(image_path: Path, api_key: str | None = None, secret_key: str | None = None) -> list[OcrChar]:
    import requests

    api_key = api_key or os.getenv("BAIDU_OCR_API_KEY")
    secret_key = secret_key or os.getenv("BAIDU_OCR_SECRET_KEY")
    if not api_key or not secret_key:
        raise RuntimeError("百度 OCR 需要环境变量 BAIDU_OCR_API_KEY 和 BAIDU_OCR_SECRET_KEY")

    token_resp = requests.post(
        "https://aip.baidubce.com/oauth/2.0/token",
        params={
            "grant_type": "client_credentials",
            "client_id": api_key,
            "client_secret": secret_key,
        },
        timeout=30,
    )
    token_resp.raise_for_status()
    token = token_resp.json().get("access_token")
    if not token:
        raise RuntimeError(f"百度 OCR 鉴权失败: {token_resp.text}")

    image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    resp = requests.post(
        f"https://aip.baidubce.com/rest/2.0/ocr/v1/accurate?access_token={token}",
        data={
            "image": image_b64,
            "recognize_granularity": "small",
            "detect_direction": "true",
            "probability": "true",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=60,
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("error_code"):
        raise RuntimeError(f"百度 OCR 返回错误: {payload.get('error_msg')}")

    chars: list[OcrChar] = []
    for line in payload.get("words_result") or []:
        for item in line.get("chars") or []:
            text = str(item.get("char") or "")
            loc = item.get("location") or {}
            if len(text) != 1:
                continue
            chars.append(
                OcrChar(
                    char=text,
                    bbox=(
                        int(loc.get("left", 0)),
                        int(loc.get("top", 0)),
                        int(loc.get("width", 0)),
                        int(loc.get("height", 0)),
                    ),
                )
            )
    return chars


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1, y1 = max(ax, bx), max(ay, by)
    x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    if inter <= 0:
        return 0.0
    union = aw * ah + bw * bh - inter
    return inter / union if union else 0.0


def labels_from_ocr(boxes: list[tuple[int, int, int, int]], ocr_chars: list[OcrChar]) -> list[str | None]:
    """每个切块取重叠最大的 OCR 字。对不上的位置留空，由调用方中止导入。"""
    used: set[int] = set()
    labels: list[str | None] = []
    for box in boxes:
        best_index = None
        best_overlap = 0.0
        for index, item in enumerate(ocr_chars):
            if index in used:
                continue
            overlap = _iou(box, item.bbox)
            if overlap > best_overlap:
                best_index = index
                best_overlap = overlap
        if best_index is None or best_overlap < 0.1:
            labels.append(None)
        else:
            used.add(best_index)
            labels.append(ocr_chars[best_index].char)
    return labels
