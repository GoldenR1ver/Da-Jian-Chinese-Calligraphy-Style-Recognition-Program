"""整页作品的切字与单字清洗。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import median

import cv2
import numpy as np

CANVAS = 128


@dataclass
class Segment:
    bbox: tuple[int, int, int, int]
    png: bytes
    gray: np.ndarray


def is_cjk(ch: str) -> bool:
    if len(ch) != 1:
        return False
    code = ord(ch)
    return (
        0x4E00 <= code <= 0x9FFF
        or 0x3400 <= code <= 0x4DBF
        or 0x20000 <= code <= 0x2A6DF
        or 0xF900 <= code <= 0xFAFF
    )


def cjk_chars(text: str) -> list[str]:
    return [ch for ch in text if is_cjk(ch)]


def load_page_gray(path: Path) -> np.ndarray:
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise FileNotFoundError(f"无法读取图片: {path}")
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    # 深色纸面先反相，后面的步骤都按「浅底深字」处理。
    if float(gray.mean()) < 110:
        gray = 255 - gray
        return gray
    blue, green, red = cv2.split(bgr)
    red16 = red.astype(np.int16)
    seal = (red16 > 140) & (red16 - green.astype(np.int16) > 40) & (red16 - blue.astype(np.int16) > 40)
    gray = gray.copy()
    gray[seal] = 255
    return gray


def ink_mask(gray: np.ndarray) -> np.ndarray:
    blur = cv2.medianBlur(gray, 3)
    _, mask = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return mask


def _should_merge(a: tuple[int, int, int, int], b: tuple[int, int, int, int], scale: float) -> bool:
    """只合并重叠或几乎贴在一起的碎片，避免把左右相邻的两个字并成一个。"""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    gap_x = max(0, max(ax, bx) - min(ax + aw, bx + bw))
    gap_y = max(0, max(ay, by) - min(ay + ah, by + bh))
    if gap_x == 0 and gap_y == 0:
        return True
    acx, acy = ax + aw / 2, ay + ah / 2
    bcx, bcy = bx + bw / 2, by + bh / 2
    dist = ((acx - bcx) ** 2 + (acy - bcy) ** 2) ** 0.5
    return dist < 0.35 * scale and min(gap_x, gap_y) <= 2


def _merge_boxes(boxes: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    if not boxes:
        return []
    scale = median(max(w, h) for _, _, w, h in boxes) or 1
    parent = list(range(len(boxes)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if _should_merge(boxes[i], boxes[j], float(scale)):
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[rj] = ri
    groups: dict[int, list[tuple[int, int, int, int]]] = {}
    for i, box in enumerate(boxes):
        groups.setdefault(find(i), []).append(box)
    merged: list[tuple[int, int, int, int]] = []
    for group in groups.values():
        x1 = min(b[0] for b in group)
        y1 = min(b[1] for b in group)
        x2 = max(b[0] + b[2] for b in group)
        y2 = max(b[1] + b[3] for b in group)
        merged.append((x1, y1, x2 - x1, y2 - y1))
    return merged


def _order_boxes(boxes: list[tuple[int, int, int, int]], layout: str) -> list[tuple[int, int, int, int]]:
    if not boxes:
        return []
    med_h = median(b[3] for b in boxes) or 1
    med_w = median(b[2] for b in boxes) or 1
    if layout == "horizontal":
        pending = sorted(boxes, key=lambda b: b[1] + b[3] / 2)
        rows: list[list[tuple[int, int, int, int]]] = []
        for box in pending:
            cy = box[1] + box[3] / 2
            placed = False
            for row in rows:
                row_cy = sum(item[1] + item[3] / 2 for item in row) / len(row)
                if abs(cy - row_cy) <= 0.55 * med_h:
                    row.append(box)
                    placed = True
                    break
            if not placed:
                rows.append([box])
        ordered: list[tuple[int, int, int, int]] = []
        for row in rows:
            row.sort(key=lambda b: b[0])
            ordered.extend(row)
        return ordered
    if layout != "vertical":
        raise ValueError("layout 只能是 horizontal 或 vertical")
    pending = sorted(boxes, key=lambda b: -(b[0] + b[2] / 2))
    columns: list[list[tuple[int, int, int, int]]] = []
    for box in pending:
        cx = box[0] + box[2] / 2
        placed = False
        for column in columns:
            col_cx = sum(item[0] + item[2] / 2 for item in column) / len(column)
            if abs(cx - col_cx) <= 0.55 * med_w:
                column.append(box)
                placed = True
                break
        if not placed:
            columns.append([box])
    ordered = []
    for column in columns:
        column.sort(key=lambda b: b[1])
        ordered.extend(column)
    return ordered


def find_boxes(mask: np.ndarray, page_shape: tuple[int, int]) -> list[tuple[int, int, int, int]]:
    height, width = page_shape
    page_area = height * width
    min_area = max(40, int(page_area * 0.0002))
    max_area = int(page_area * 0.92)
    kernel = max(3, int(round(min(height, width) / 200)) | 1)
    closed = cv2.morphologyEx(
        mask,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (kernel, kernel)),
    )
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes: list[tuple[int, int, int, int]] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        if area < min_area or area > max_area:
            continue
        if w < 2 or h < 2:
            continue
        if w >= int(width * 0.98) and h >= int(height * 0.98):
            continue
        boxes.append((int(x), int(y), int(w), int(h)))
    return _merge_boxes(boxes)


def clean_glyph(gray: np.ndarray, bbox: tuple[int, int, int, int], canvas: int = CANVAS) -> np.ndarray:
    x, y, w, h = bbox
    pad = max(2, int(0.08 * max(w, h)))
    height, width = gray.shape[:2]
    x0, y0 = max(0, x - pad), max(0, y - pad)
    x1, y1 = min(width, x + w + pad), min(height, y + h + pad)
    crop = gray[y0:y1, x0:x1]
    if crop.size == 0:
        raise ValueError("切出的字块是空的")
    blur = cv2.medianBlur(crop, 3)
    ink = ink_mask(blur)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    cleaned = np.zeros_like(ink)
    area_min = max(8, int(0.01 * ink.size))
    for index in range(1, count):
        if int(stats[index, cv2.CC_STAT_AREA]) >= area_min:
            cleaned[labels == index] = 255
    ys, xs = np.where(cleaned > 0)
    if len(xs) == 0:
        raise ValueError("清洗后没有留下笔画")
    cleaned = cleaned[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    ink_black = 255 - cleaned
    ch, cw = ink_black.shape
    margin = 8
    inner = canvas - 2 * margin
    scale = min(inner / ch, inner / cw)
    resized_w = max(1, int(round(cw * scale)))
    resized_h = max(1, int(round(ch * scale)))
    resized = cv2.resize(ink_black, (resized_w, resized_h), interpolation=cv2.INTER_AREA)
    board = np.full((canvas, canvas), 255, np.uint8)
    ox = (canvas - resized_w) // 2
    oy = (canvas - resized_h) // 2
    board[oy : oy + resized_h, ox : ox + resized_w] = resized
    return board


def encode_png(gray: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", gray)
    if not ok:
        raise RuntimeError("单字图编码失败")
    return buf.tobytes()


def decode_png(blob: bytes) -> np.ndarray:
    arr = np.frombuffer(blob, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError("无法解码字库中的单字图")
    return image


def split_page(path: Path, layout: str) -> tuple[np.ndarray, list[Segment]]:
    gray = load_page_gray(path)
    boxes = _order_boxes(find_boxes(ink_mask(gray), gray.shape[:2]), layout)
    segments: list[Segment] = []
    for bbox in boxes:
        glyph = clean_glyph(gray, bbox)
        segments.append(Segment(bbox=bbox, png=encode_png(glyph), gray=glyph))
    return gray, segments


def write_debug(segments: list[Segment], labels: list[str | None], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for index, segment in enumerate(segments):
        label = labels[index] if index < len(labels) and labels[index] else "unknown"
        target = directory / f"{index:03d}_{label}.png"
        target.write_bytes(segment.png)
