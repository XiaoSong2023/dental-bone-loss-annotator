"""牙位分割 —— 可插拔接口。

首版用 ManualSegmenter：你在全景片上点一下某颗牙，它给出一个**必然包含完整
牙冠 + 牙根 + 根尖**的 ROI 并放大。不依赖任何模型权重。

将来拿到 ONNX 权重时，把它放进 models/ 目录，OnnxYoloSegmenter 会自动启用，
上层代码一行都不用改。

调研结论（见 docs/架构与需求.md §14）：
  · 用户最初指定的 Odontoai171 仓库经核实**不含权重**，只有训练脚本。
  · 公开的全景片权重几乎都只有单类 "tooth"，不带 FDI 牙位号。
  ⇒ 因此牙位号与分割**解耦**：牙位号由牙弓几何规则推断 + 人工可改（见 guess_fdi）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class ToothInstance:
    bbox: tuple[float, float, float, float]     # x, y, w, h（原图坐标）
    fdi: int | None = None
    score: float = 1.0
    mask: np.ndarray | None = None


class ToothSegmenter(ABC):
    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def segment(self, gray: np.ndarray) -> list[ToothInstance]: ...


# ── 首版：手动 ──────────────────────────────────────────────────────────


class ManualSegmenter(ToothSegmenter):
    """不做实例分割。由点击点自适应生成 ROI。"""

    def available(self) -> bool:
        return True

    def segment(self, gray: np.ndarray) -> list[ToothInstance]:
        return []

    @staticmethod
    def roi_at(gray: np.ndarray, x: float, y: float,
               y_occlusal: float | None = None,
               width_frac: float = 0.075,
               height_frac: float = 0.42) -> tuple[float, float, float, float]:
        """以点击点为中心生成单牙 ROI。

        宽度取图像宽的一个固定比例（约一颗磨牙的宽度余量），
        高度**向牙根方向多留**，确保根尖不被切掉 —— 你明确要求「不能残缺」。
        ROI 始终钳制在图像边界内。
        """
        H, W = gray.shape[:2]
        w = max(60.0, W * width_frac)
        h = max(120.0, H * height_frac)

        if y_occlusal is None:
            y_occlusal = H * 0.5
        # 上颌（点击点在咬合线上方）根尖朝上 → 向上多留；下颌反之
        upward = y < y_occlusal
        crown_margin, root_margin = 0.30, 0.70
        if upward:
            y0 = y - h * root_margin
        else:
            y0 = y - h * crown_margin

        x0 = x - w / 2
        x0 = max(0.0, min(x0, W - w))
        y0 = max(0.0, min(y0, max(0.0, H - h)))
        return (x0, y0, min(w, W), min(h, H))


# ── 预留：ONNX ──────────────────────────────────────────────────────────


class OnnxYoloSegmenter(ToothSegmenter):
    """把 *.onnx 放进 models/ 即自动启用。无权重时 available() 返回 False，
    界面上的「自动分割」按钮保持灰显并给出提示。

    解码逻辑将复用 ibaiGorordo/ONNX-YOLOv8-Instance-Segmentation（MIT 许可）。
    """

    def __init__(self, models_dir: Path):
        self.models_dir = Path(models_dir)
        self._session = None
        self._path: Path | None = None

    def find_model(self) -> Path | None:
        if not self.models_dir.exists():
            return None
        return next(iter(sorted(self.models_dir.glob("*.onnx"))), None)

    def available(self) -> bool:
        if self.find_model() is None:
            return False
        try:
            import onnxruntime  # noqa: F401
        except ImportError:
            return False
        return True

    def unavailable_reason(self) -> str:
        if self.find_model() is None:
            return (
                f"未找到分割模型。把 YOLO-seg 的 .onnx 权重放进 {self.models_dir} 即可启用。\n"
                "注意：请用 n / s 尺寸（7–24MB）；l / x 尺寸导出后有 126 / 230MB，会超出体积预算。"
            )
        try:
            import onnxruntime  # noqa: F401
        except ImportError:
            return "缺少 onnxruntime，请执行：pip install onnxruntime"
        return ""

    def segment(self, gray: np.ndarray) -> list[ToothInstance]:
        if not self.available():
            return []
        raise NotImplementedError("ONNX 推理将在 M5 阶段接入")


# ── 牙位号推断（与分割解耦） ──────────────────────────────────────────────


def guess_fdi(x: float, y: float, image_w: int, image_h: int,
              y_occlusal: float | None = None,
              existing: dict[int, float] | None = None) -> int | None:
    """由点击位置粗猜 FDI 牙位号。

    规则：
      1. 咬合线上/下 → 上颌 / 下颌
      2. 图像中线左/右 → 象限 1/2（上）或 4/3（下）
         注意全景片是「面向观察者」，图像左侧 = 患者右侧
      3. 距中线的水平距离按 8 等分 → 牙序 1…8

    牙列完整时基本准确，缺牙 / 阻生时会偏一位 —— 界面上牙位号是可改的下拉框，
    3 秒即可修正。这是标注工具的正确取舍，不必为此绑一个 2.5GB 的模型。
    """
    if image_w <= 0 or image_h <= 0:
        return None
    if y_occlusal is None:
        y_occlusal = image_h * 0.5

    upper = y < y_occlusal
    mid = image_w / 2.0
    patient_right = x < mid                 # 图像左 = 患者右

    quadrant = (1 if patient_right else 2) if upper else (4 if patient_right else 3)

    half = max(mid, 1.0)
    # 牙弓两侧各约占半幅宽度的 88%，8 颗牙均分
    span = half * 0.88
    dist = min(abs(x - mid), span)
    seq = int(dist / (span / 8)) + 1
    seq = max(1, min(8, seq))

    return quadrant * 10 + seq
