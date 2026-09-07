"""公式引擎 —— **改公式的唯一入口**。

架构第一原则：JSON 里永远只存原始点坐标，比值是运行时算出来的派生量。
所以换公式后，对已有的 70 张标注点「重算」即可，**无需重标**。

新增一个公式 = 写一个函数 + 一行 @formula 装饰器。
界面「设置 → 计算公式」的下拉框会自动出现新选项。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping

from . import geometry as g

# ── 计算结果 ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Metrics:
    """单个测量位点（一个邻面）的计算结果。"""

    root_length: float          # 根长，像素
    bone_loss: float            # 骨吸收距离，像素（可为负）
    ratio: float                # 骨吸收比例 = bone_loss / root_length
    warnings: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return "too_short" not in self.warnings

    @property
    def no_loss(self) -> bool:
        """AC 位于 CEJ 冠方 —— 未见骨吸收。比值如实保留负号，不截断为 0。"""
        return self.bone_loss < 0


class FormulaError(ValueError):
    """点位不足或几何退化，无法计算。"""


# ── 注册表 ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Formula:
    id: str
    label: str
    needs: tuple[str, ...]      # 需要哪些点，如 ("cej", "ac", "apex")
    fn: Callable[[Mapping[str, g.Vec], "FormulaConfig"], Metrics]
    description: str = ""

    def __call__(self, points: Mapping[str, g.Vec], cfg: "FormulaConfig") -> Metrics:
        missing = [k for k in self.needs if points.get(k) is None]
        if missing:
            raise FormulaError(f"缺少点位: {', '.join(missing)}")
        return self.fn(points, cfg)


@dataclass
class FormulaConfig:
    """公式的可调参数。来自 config/grading.json 的 validation 段。"""

    min_root_px: float = 20.0
    ratio_warn_above: float = 1.0


FORMULAS: dict[str, Formula] = {}
DEFAULT_FORMULA_ID = "projection_v1"


def formula(fid: str, label: str, needs: Iterable[str], description: str = ""):
    """把一个函数注册成可选公式。"""

    def deco(fn):
        FORMULAS[fid] = Formula(fid, label, tuple(needs), fn, description)
        return fn

    return deco


def get(fid: str | None) -> Formula:
    """按 id 取公式；未知 id 回退到默认公式（保证旧数据仍能打开）。"""
    return FORMULAS.get(fid or "", FORMULAS[DEFAULT_FORMULA_ID])


def choices() -> list[tuple[str, str]]:
    """(id, label) 列表，供界面下拉框使用。"""
    return [(f.id, f.label) for f in FORMULAS.values()]


# ── 内置公式 ────────────────────────────────────────────────────────────


def _common_warnings(root_length: float, ratio: float, cfg: FormulaConfig) -> tuple[str, ...]:
    w: list[str] = []
    if root_length < cfg.min_root_px:
        w.append("too_short")
    if ratio > cfg.ratio_warn_above:
        w.append("ratio_gt_1")     # AC 越过根尖，理论上不可能，提示复核
    if ratio < 0:
        w.append("no_loss")        # AC 在 CEJ 冠方，未见吸收
    return tuple(w)


# 四个公式，两两成对。全部用**同一组手标的点**，差别只有两处：
#
#   起点：CEJ（①②）      还是  CEJ 下 2mm（③④）
#   分子：两点直线距离（①③）还是  沿牙长轴的投影（②④）
#
#   终点从来不变：分子终点是牙槽嵴顶 AC，分母终点是根尖。
#
# ⇒ 标满 4 个点后四个公式的结果同时可得，切换下拉框即可，永远不用重标。


def _direct(origin: str, p: Mapping[str, g.Vec], cfg: FormulaConfig) -> Metrics:
    """直线法：分子分母都取两点直线距离。"""
    o = p[origin]
    root_length = g.distance(p["apex"], o)
    if root_length < g.EPS:
        raise FormulaError("起点与根尖重合")
    bone_loss = g.distance(p["ac"], o)
    ratio = bone_loss / root_length
    return Metrics(root_length, bone_loss, ratio, _common_warnings(root_length, ratio, cfg))


def _projection(origin: str, p: Mapping[str, g.Vec], cfg: FormulaConfig) -> Metrics:
    """投影法：分子改取 (AC−起点) 在「起点→根尖」长轴上的有符号投影。"""
    o = p[origin]
    axis = g.sub(p["apex"], o)
    root_length = g.norm(axis)
    if root_length < g.EPS:
        raise FormulaError("起点与根尖重合，无法确定长轴")
    bone_loss = g.projection_length(g.sub(p["ac"], o), axis)
    ratio = bone_loss / root_length
    return Metrics(root_length, bone_loss, ratio, _common_warnings(root_length, ratio, cfg))


@formula(
    "direct_v1",
    label="① 直线法（不投影）：CEJ→牙槽嵴顶 ÷ CEJ→根尖",
    needs=("cej", "ac", "apex"),
    description=(
        "分子取 CEJ 到牙槽嵴顶的直线距离，分母取 CEJ 到根尖的直线距离。\n"
        "传统手工测量的做法。注意：AC 点通常偏在牙的侧方，直线距离会把这段"
        "侧向分量也算进去，牙齿越倾斜高估越多。"
    ),
)
def direct_v1(p: Mapping[str, g.Vec], cfg: FormulaConfig) -> Metrics:
    return _direct("cej", p, cfg)


@formula(
    "projection_v1",
    label="② 投影法（推荐）：①式投影到牙长轴后再相除",
    needs=("cej", "ac", "apex"),
    description=(
        "长轴 = CEJ→根尖。分子改取 (AC−CEJ) 在长轴上的有符号投影，"
        "剔除 AC 偏在牙侧方带来的横向分量；分母仍是 ‖根尖−CEJ‖。\n"
        "牙齿倾斜、弯根时比直线法稳健得多，两者差值即倾斜带来的高估量。"
    ),
)
def projection_v1(p: Mapping[str, g.Vec], cfg: FormulaConfig) -> Metrics:
    return _projection("cej", p, cfg)


@formula(
    "direct_cej2_v1",
    label="③ 直线法·CEJ下2mm 起点：CEJ-2mm→牙槽嵴顶 ÷ CEJ-2mm→根尖",
    needs=("cej", "cej2", "ac", "apex"),
    description=(
        "与①同为直线距离之比，只是**起点从 CEJ 换成 CEJ 下 2mm**（P2），"
        "终点不变（分子到牙槽嵴顶、分母到根尖）。\n"
        "生理性骨改建约占 CEJ 下 2mm，从这里起算可把它排除在「病理性吸收」之外。"
    ),
)
def direct_cej2_v1(p: Mapping[str, g.Vec], cfg: FormulaConfig) -> Metrics:
    return _direct("cej2", p, cfg)


@formula(
    "projection_cej2_v1",
    label="④ 投影法·CEJ下2mm 起点：③式投影到牙长轴后再相除",
    needs=("cej", "cej2", "ac", "apex"),
    description=(
        "长轴 = CEJ-2mm→根尖。分子取 (AC−CEJ-2mm) 在该轴上的有符号投影，"
        "分母是 ‖根尖−CEJ-2mm‖。\n"
        "= ③ 排除生理性骨改建 + ② 排除牙齿倾斜，两个修正同时生效。"
    ),
)
def projection_cej2_v1(p: Mapping[str, g.Vec], cfg: FormulaConfig) -> Metrics:
    return _projection("cej2", p, cfg)


# ── 再加公式怎么写 ────────────────────────────────────────────────────
#
# 只换算法、不加新点位（10 分钟）：
#
#   @formula("my_v1", label="⑤ 我的公式", needs=("cej", "ac", "apex"))
#   def my_v1(p, cfg):
#       L = g.distance(p["apex"], p["cej"])
#       h = ...
#       return Metrics(L, h, h / L, _common_warnings(L, h / L, cfg))
#
# 需要新点位（半天）：照 cej2 的样子走一遍 ——
#   1. models.ROLES 里加角色（顺序即标定顺序，也决定 P 编号）
#   2. models.Site 加同名字段
#   3. 这里加公式，needs 写上新角色
# 标定对话框、点编号、导出列都是从 ROLES 自动派生的，不用逐处改。
# 旧数据缺新点位时，需要它的公式自动算不出、老公式照常可用。
