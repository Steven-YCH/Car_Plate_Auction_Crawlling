"""OCR fallback utilities for auction PDFs.

Primary engine is RapidOCR (onnxruntime), which is lighter than PaddleOCR.
PaddleOCR remains supported if installed. OCR is only used when native PDF
text is missing/garbled (common for older TD TVRM handouts).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import fitz

from .config import parsing as parsing_cfg


@dataclass
class OCRConfig:
    engine: str = parsing_cfg.ocr_engine
    zoom: float = 2.0


_OCR_SINGLETON: Any = None


def text_looks_garbled(lines: List[str], *, min_ascii_ratio: float = 0.65) -> bool:
    """Heuristic for broken ToUnicode / custom-encoded PDFs."""

    if not lines:
        return True
    total = sum(len(l) for l in lines) or 1
    good = sum(
        1
        for l in lines
        for ch in l
        if ch.isascii() and (ch.isalnum() or ch in " ,@$/.-:*()[]")
    )
    return (good / total) < min_ascii_ratio


def _ensure_ocr(engine: str):
    global _OCR_SINGLETON
    if _OCR_SINGLETON is not None:
        return _OCR_SINGLETON

    if engine in {"rapid", "auto"}:
        try:
            from rapidocr_onnxruntime import RapidOCR

            _OCR_SINGLETON = ("rapid", RapidOCR())
            return _OCR_SINGLETON
        except Exception:
            if engine == "rapid":
                raise RuntimeError(
                    "RapidOCR is required for OCR fallback but is not installed. "
                    "Install with: pip install rapidocr-onnxruntime onnxruntime"
                )

    if engine in {"paddle", "auto"}:
        try:
            from paddleocr import PaddleOCR  # type: ignore

            _OCR_SINGLETON = ("paddle", PaddleOCR(lang="ch", show_log=False))
            return _OCR_SINGLETON
        except Exception as exc:
            raise RuntimeError(
                "No OCR engine available. Install rapidocr-onnxruntime "
                "(recommended) or paddleocr, or disable OCR via "
                "config.parsing.use_ocr_fallback = False."
            ) from exc

    raise ValueError(f"Unsupported OCR engine: {engine!r}")


def extract_ocr_items(doc: fitz.Document, *, cfg: OCRConfig | None = None) -> List[Dict[str, Any]]:
    """Return OCR items with approximate centers: {cx, cy, text, score}."""

    if cfg is None:
        cfg = OCRConfig()

    engine_name, engine = _ensure_ocr(cfg.engine)
    items: List[Dict[str, Any]] = []

    for page in doc:
        pix = page.get_pixmap(matrix=fitz.Matrix(cfg.zoom, cfg.zoom))
        img_bytes = pix.tobytes("png")

        if engine_name == "rapid":
            # RapidOCR accepts numpy array / path / bytes depending on version.
            import numpy as np

            arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            if pix.n == 4:
                arr = arr[:, :, :3]
            result, _elapse = engine(arr)
            for entry in result or []:
                box, text, score = entry[0], entry[1], entry[2]
                xs = [p[0] for p in box]
                ys = [p[1] for p in box]
                items.append(
                    {
                        "cx": sum(xs) / 4.0,
                        "cy": sum(ys) / 4.0,
                        "text": (text or "").strip(),
                        "score": score,
                    }
                )
        else:
            result = engine.ocr(img_bytes)
            for line in result or []:
                if not line:
                    continue
                try:
                    box, (text, score) = line[0], line[1]
                except Exception:
                    continue
                xs = [p[0] for p in box]
                ys = [p[1] for p in box]
                t = (text or "").strip()
                if not t:
                    continue
                items.append(
                    {
                        "cx": sum(xs) / 4.0,
                        "cy": sum(ys) / 4.0,
                        "text": t,
                        "score": score,
                    }
                )
    return items


def ocr_extract_lines(doc: fitz.Document, *, cfg: OCRConfig | None = None) -> List[str]:
    items = extract_ocr_items(doc, cfg=cfg)
    # Reading order: top-to-bottom, then left-to-right.
    items_sorted = sorted(items, key=lambda it: (round(it["cy"] / 8) * 8, it["cx"]))
    return [it["text"] for it in items_sorted if it.get("text")]


def extract_text_lines_with_fallback(doc: fitz.Document) -> List[str]:
    """Return text lines from a PDF document with optional OCR fallback."""

    lines: List[str] = []
    for i, page in enumerate(doc):
        if parsing_cfg.max_pages is not None and i >= parsing_cfg.max_pages:
            break
        text = page.get_text()
        for raw in text.splitlines():
            ln = raw.strip()
            if ln:
                lines.append(ln)

    if lines and not text_looks_garbled(lines):
        return lines
    if not parsing_cfg.use_ocr_fallback:
        return lines
    return ocr_extract_lines(doc)
