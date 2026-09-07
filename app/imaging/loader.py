"""图像读取与实时增强。

⚠️ Windows 上 `cv2.imread` 遇到中文路径会静默返回 None
   （OpenCV 内部用 ANSI 编码打开文件）。本项目的路径本身就带中文，
   所以一律走 `np.fromfile` + `cv2.imdecode`，写文件同理用 `imencode` + `tofile`。

本模块只用 numpy / cv2，不 import Qt —— numpy→QImage 的转换在 ui 层做。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


def imread_unicode(path: Path, flags: int = cv2.IMREAD_GRAYSCALE) -> np.ndarray | None:
    """支持中文/Unicode 路径的图像读取。"""
    try:
        buf = np.fromfile(str(path), dtype=np.uint8)
    except OSError:
        return None
    if buf.size == 0:
        return None
    img = cv2.imdecode(buf, flags)
    return img


def imwrite_unicode(path: Path, img: np.ndarray) -> bool:
    """支持中文路径的图像写出。"""
    ok, buf = cv2.imencode(Path(path).suffix or ".png", img)
    if not ok:
        return False
    try:
        buf.tofile(str(path))
    except OSError:
        return False
    return True


def load_gray(path: Path) -> np.ndarray | None:
    """读成 8 位灰度。全景片本身就是灰度，彩色输入自动转换。"""
    img = imread_unicode(path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    if img.dtype != np.uint8:                       # 16 位 TIFF 之类
        img = cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    return img


# ── 实时增强 ────────────────────────────────────────────────────────────


@dataclass
class ImageAdjust:
    """看片参数。前牙区牙根重叠、上颌窦干扰时用来把 AC 点看清楚。"""

    brightness: int = 0          # −100 … +100
    contrast: int = 0            # −100 … +100
    gamma: float = 1.0           # 0.2 … 3.0
    clahe: bool = False          # 局部对比度增强（全景片明暗不均时很有效）
    clahe_clip: float = 2.0
    invert: bool = False         # 反相，有时更容易看清骨嵴边缘

    @property
    def is_identity(self) -> bool:
        return (
            self.brightness == 0 and self.contrast == 0
            and abs(self.gamma - 1.0) < 1e-6
            and not self.clahe and not self.invert
        )

    def reset(self) -> None:
        self.__init__()          # type: ignore[misc]


_GAMMA_CACHE: dict[int, np.ndarray] = {}


def _gamma_lut(gamma: float) -> np.ndarray:
    key = int(round(gamma * 1000))
    lut = _GAMMA_CACHE.get(key)
    if lut is None:
        inv = 1.0 / max(gamma, 1e-3)
        lut = np.clip(((np.arange(256) / 255.0) ** inv) * 255.0, 0, 255).astype(np.uint8)
        if len(_GAMMA_CACHE) > 64:
            _GAMMA_CACHE.clear()
        _GAMMA_CACHE[key] = lut
    return lut


def apply_adjust(gray: np.ndarray, adj: ImageAdjust) -> np.ndarray:
    """按看片参数处理灰度图。不改原图，返回新数组。"""
    if adj.is_identity:
        return gray
    out = gray
    if adj.clahe:
        clahe = cv2.createCLAHE(clipLimit=max(0.1, adj.clahe_clip), tileGridSize=(8, 8))
        out = clahe.apply(out)
    if adj.contrast or adj.brightness:
        # contrast −100…+100 → alpha 0.5…2.5
        alpha = 1.0 + (adj.contrast / 100.0) * (1.5 if adj.contrast > 0 else 0.5)
        beta = adj.brightness * 1.28
        out = cv2.convertScaleAbs(out, alpha=alpha, beta=beta)
    if abs(adj.gamma - 1.0) > 1e-6:
        out = cv2.LUT(out, _gamma_lut(adj.gamma))
    if adj.invert:
        out = cv2.bitwise_not(out)
    return out


def thumbnail(gray: np.ndarray, max_side: int = 220) -> np.ndarray:
    h, w = gray.shape[:2]
    scale = min(1.0, max_side / max(h, w))
    if scale >= 1.0:
        return gray
    return cv2.resize(gray, (max(1, int(w * scale)), max(1, int(h * scale))),
                      interpolation=cv2.INTER_AREA)


def crop_roi(gray: np.ndarray, roi: tuple[float, float, float, float]) -> tuple[np.ndarray, tuple[int, int]]:
    """按 ROI 裁剪，返回 (子图, 左上角原图坐标)。ROI 自动钳制在图像内。"""
    h, w = gray.shape[:2]
    x, y, rw, rh = roi
    x0 = max(0, int(round(x)))
    y0 = max(0, int(round(y)))
    x1 = min(w, int(round(x + rw)))
    y1 = min(h, int(round(y + rh)))
    if x1 <= x0 or y1 <= y0:
        return gray, (0, 0)
    return gray[y0:y1, x0:x1], (x0, y0)
