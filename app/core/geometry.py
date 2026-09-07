"""纯二维几何运算。

刻意不 import 任何 Qt / OpenCV —— 保证公式与测量逻辑可脱离界面单元测试。
坐标一律使用图像像素坐标系：x 向右，y 向下。
"""

from __future__ import annotations

import math

Vec = tuple[float, float]

EPS = 1e-9


def sub(a: Vec, b: Vec) -> Vec:
    """向量 a − b。"""
    return (a[0] - b[0], a[1] - b[1])


def add(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1])


def scale(a: Vec, k: float) -> Vec:
    return (a[0] * k, a[1] * k)


def dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1]


def norm(a: Vec) -> float:
    return math.hypot(a[0], a[1])


def distance(a: Vec, b: Vec) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def normalize(a: Vec) -> Vec:
    """单位化。零向量返回 (0, 0)。"""
    n = norm(a)
    if n < EPS:
        return (0.0, 0.0)
    return (a[0] / n, a[1] / n)


def projection_length(vec: Vec, axis: Vec) -> float:
    """vec 在 axis 方向上的**有符号**投影长度。

    符号约定：与 axis 同向为正，反向为负。
    这正是骨吸收距离 h 的定义 —— AC 位于 CEJ 根方（与长轴同向）时为正。
    """
    n = norm(axis)
    if n < EPS:
        return 0.0
    return dot(vec, axis) / n


def foot_of_perpendicular(p: Vec, a: Vec, b: Vec) -> Vec:
    """点 p 到直线 ab 的垂足。

    仅用于界面上把「AC 到长轴的投影关系」画出来，不参与数值计算。
    直线退化为一点时返回 a。
    """
    ab = sub(b, a)
    n2 = dot(ab, ab)
    if n2 < EPS:
        return a
    t = dot(sub(p, a), ab) / n2
    return add(a, scale(ab, t))


def point_to_segment_distance(p: Vec, a: Vec, b: Vec) -> float:
    """点到线段的最短距离（命中测试用）。"""
    ab = sub(b, a)
    n2 = dot(ab, ab)
    if n2 < EPS:
        return distance(p, a)
    t = max(0.0, min(1.0, dot(sub(p, a), ab) / n2))
    return distance(p, add(a, scale(ab, t)))


def angle_deg(a: Vec, b: Vec) -> float:
    """两向量夹角（度，0–180）。用于界面提示牙轴是否异常。"""
    na, nb = norm(a), norm(b)
    if na < EPS or nb < EPS:
        return 0.0
    c = max(-1.0, min(1.0, dot(a, b) / (na * nb)))
    return math.degrees(math.acos(c))
