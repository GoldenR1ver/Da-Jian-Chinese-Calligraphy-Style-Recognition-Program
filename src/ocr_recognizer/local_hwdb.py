from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import cv2
import torch
from torchvision import transforms
from ..character_recognizer.model import LeNet, ResNet, VGG


@dataclass
class LocalHwdbConfig:
    model_name: str = "ResNet"
    image_size: int = 64
    min_area: int = 20

    # Default to paths inside src/character_recognizer
    model_path: Optional[str] = None
    char_dict_path: Optional[str] = None
    use_cuda: bool = False


class LocalHwdbOcrEngine:
    """Local OCR adapter for src/character_recognizer model."""

    def __init__(self, config: Optional[LocalHwdbConfig] = None) -> None:
        self.config = config or LocalHwdbConfig()
        self._loaded = False
        self._model = None
        self._idx_to_char: dict[int, str] = {}
        self._device = torch.device("cpu")

    def _component_root(self) -> Path:
        return Path(__file__).resolve().parents[1] / "character_recognizer"

    def _ensure_paths(self) -> tuple[Path, Path, Path]:
        root = self._component_root()
        model_path = Path(self.config.model_path) if self.config.model_path else root / "result" / "param" / "model.pth"
        dict_path = Path(self.config.char_dict_path) if self.config.char_dict_path else root / "data" / "char_dict"
        return root, model_path, dict_path

    def _lazy_load(self) -> None:
        if self._loaded:
            return

        root, model_path, dict_path = self._ensure_paths()
        if not model_path.exists():
            raise FileNotFoundError(f"Local model not found: {model_path}")
        if not dict_path.exists():
            raise FileNotFoundError(f"Local char_dict not found: {dict_path}")

        model_dict = {"LeNet": LeNet, "VGG": VGG, "ResNet": ResNet}
        if self.config.model_name not in model_dict:
            raise ValueError(f"Unsupported model_name: {self.config.model_name}")

        use_cuda = self.config.use_cuda and torch.cuda.is_available()
        self._device = torch.device("cuda" if use_cuda else "cpu")

        model = model_dict[self.config.model_name]().to(self._device)
        state = torch.load(str(model_path), map_location=self._device)
        model.load_state_dict(state)
        model.eval()
        self._model = model

        with open(dict_path, "rb") as f:
            char_dict = pickle.load(f)
            self._idx_to_char = {v: k for k, v in char_dict.items()}

        self._loaded = True

    def _segment_chars(self, image_bgr: Any) -> list[dict[str, Any]]:
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        boxes: list[tuple[int, int, int, int]] = []
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            if w * h >= self.config.min_area:
                boxes.append((x, y, w, h))
        boxes.sort(key=lambda b: b[0])

        chars: list[dict[str, Any]] = []
        for x, y, w, h in boxes:
            chars.append(
                {
                    "crop": binary[y : y + h, x : x + w],
                    "location": {"left": int(x), "top": int(y), "width": int(w), "height": int(h)},
                }
            )
        return chars

    def _predict_char(self, binary_crop: Any) -> tuple[str, float]:
        self._lazy_load()
        assert self._model is not None

        x, y, w, h = cv2.boundingRect(binary_crop)
        roi = binary_crop[y : y + h, x : x + w]
        resized = cv2.resize(roi, (self.config.image_size, self.config.image_size))

        transform = transforms.ToTensor()
        tensor = transform(resized).unsqueeze(0).to(self._device)

        with torch.no_grad():
            logits = self._model(tensor)
            probs = torch.softmax(logits, dim=1)
            conf, pred = torch.max(probs, 1)

        pred_idx = int(pred.item())
        confidence = float(conf.item())
        char = self._idx_to_char.get(pred_idx, "")
        return char, confidence

    def recognize(self, image_path: str) -> dict[str, Any]:
        image = cv2.imread(image_path, cv2.IMREAD_COLOR)
        if image is None:
            return {"error": "无法读取图像", "image_path": image_path}

        segments = self._segment_chars(image)
        if not segments:
            return {
                "text": "",
                "words_result_num": 0,
                "words_result": [],
                "ocr_engine": "local_hwdb",
            }

        chars_out: list[dict[str, Any]] = []
        texts: list[str] = []
        confidences: list[float] = []

        for seg in segments:
            ch, conf = self._predict_char(seg["crop"])
            if not ch:
                continue
            texts.append(ch)
            confidences.append(conf)
            chars_out.append({"char": ch, "location": seg["location"], "probability": conf})

        text = "".join(texts)
        if chars_out:
            left = min(c["location"]["left"] for c in chars_out)
            top = min(c["location"]["top"] for c in chars_out)
            right = max(c["location"]["left"] + c["location"]["width"] for c in chars_out)
            bottom = max(c["location"]["top"] + c["location"]["height"] for c in chars_out)
            line_loc = {"left": left, "top": top, "width": right - left, "height": bottom - top}
        else:
            line_loc = {"left": 0, "top": 0, "width": 0, "height": 0}

        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        return {
            "text": text,
            "words_result_num": 1 if text else 0,
            "words_result": [{"words": text, "location": line_loc, "chars": chars_out, "probability": {"average": avg_conf}}],
            "ocr_engine": "local_hwdb",
        }

