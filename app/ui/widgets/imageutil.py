"""numpy ↔ Qt 的转换。UI 层唯一接触像素缓冲区的地方。"""

from __future__ import annotations

import numpy as np
from PySide6.QtGui import QImage, QPixmap


def gray_to_qimage(arr: np.ndarray) -> QImage:
    """8 位灰度 numpy 数组 → QImage。

    必须 copy()：QImage 不接管 numpy 的内存，数组被回收后画面会变成花屏。
    """
    arr = np.ascontiguousarray(arr)
    h, w = arr.shape[:2]
    img = QImage(arr.data, w, h, arr.strides[0], QImage.Format.Format_Grayscale8)
    return img.copy()


def gray_to_qpixmap(arr: np.ndarray) -> QPixmap:
    return QPixmap.fromImage(gray_to_qimage(arr))
