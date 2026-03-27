"""OCR adapters. Heavy deps (torch) load only when using local_hwdb."""

from __future__ import annotations

from typing import Any

from .ocr import ocr_recognize, parse_ocr_result

__all__ = [
    "ocr_recognize",
    "parse_ocr_result",
    "LocalHwdbConfig",
    "LocalHwdbOcrEngine",
]


def __getattr__(name: str) -> Any:
    if name in ("LocalHwdbConfig", "LocalHwdbOcrEngine"):
        from .local_hwdb import LocalHwdbConfig, LocalHwdbOcrEngine

        return {"LocalHwdbConfig": LocalHwdbConfig, "LocalHwdbOcrEngine": LocalHwdbOcrEngine}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
