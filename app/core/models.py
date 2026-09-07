"""数据模型。

⚠️ 架构约束：本模块只存**原始点坐标**，绝不持久化任何比值。
   所有派生量（metrics / worst / 区间）都是运行时算出来的属性。
   这样换公式后一键重算即可，不用重标。

⚠️ 本模块不 import Qt。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import copy
import math
from typing import Literal, Optional
from uuid import uuid4

from . import formula as F
from . import geometry as g
from .grading import GradingConfig, interval_of

Surface = Literal["mesial", "distal"]
SURFACES: tuple[Surface, Surface] = ("mesial", "distal")
SURFACE_LABEL = {"mesial": "近中", "distal": "远中"}

# 每个位点内点的采集顺序（也是 P 编号的顺序）：从咬合面向根尖依次标
ROLES = ("cej", "cej2", "ac", "apex")
ROLE_LABEL = {
    "cej": "CEJ 釉牙骨质界",
    "cej2": "CEJ 下 2mm",
    "ac": "AC 牙槽嵴顶",
    "apex": "根尖",
}
ROLE_SHORT = {"cej": "CEJ", "cej2": "CEJ-2mm", "ac": "AC", "apex": "根尖"}

POINTS_PER_SITE = len(ROLES)          # 4
POINTS_PER_TOOTH = POINTS_PER_SITE * len(SURFACES)   # 8

# 在灰度全景片上高辨识度的配色（每颗牙一色）。
# 与 ui/theme.py 里的同名常量保持一致 —— core 不依赖 Qt，所以这里内联一份。
TOOTH_COLORS = [
    "#22D3EE",  # 青
    "#FBBF24",  # 琥珀
    "#F87171",  # 珊瑚
    "#A78BFA",  # 藤
    "#FB923C",  # 橙
    "#F472B6",  # 桃
    "#38BDF8",  # 空
    "#FDE047",  # 黄
]
CREST_CURVE_COLOR = "#3DDC84"          # 牙槽嵴顶曲线


def point_number(tooth_index: int, surface: Surface, role: str) -> int:
    """第 n 颗牙的点编号：P(8n−7) … P(8n)。

    tooth_index 从 0 开始，所以第 1 颗牙（index=0）是 P1…P8：
        近中 CEJ=P1  CEJ-2mm=P2  AC=P3  根尖=P4
        远中 CEJ=P5  CEJ-2mm=P6  AC=P7  根尖=P8
    第 2 颗牙从 P9 开始，以此类推。跳过某侧时该侧编号留空不复用。
    """
    base = tooth_index * POINTS_PER_TOOTH
    offset = SURFACES.index(surface) * POINTS_PER_SITE + ROLES.index(role)
    return base + offset + 1


def point_label(tooth_index: int, surface: Surface, role: str) -> str:
    return f"P{point_number(tooth_index, surface, role)}"


# ── 点 ──────────────────────────────────────────────────────────────────


@dataclass
class Pt:
    """图像原始像素坐标系下的一个点。"""

    x: float
    y: float

    def __post_init__(self):
        self.x, self.y = float(self.x), float(self.y)
        if not math.isfinite(self.x) or not math.isfinite(self.y):
            raise ValueError("点坐标必须是有限数值")

    def as_tuple(self) -> g.Vec:
        return (self.x, self.y)

    def to_dict(self, label: str = "") -> dict:
        d = {"x": self.x, "y": self.y}
        if label:
            d["label"] = label
        return d

    @classmethod
    def from_dict(cls, d: dict | None) -> Optional["Pt"]:
        if not d:
            return None
        return cls(float(d["x"]), float(d["y"]))


# ── 测量位点（一个邻面） ──────────────────────────────────────────────────


@dataclass
class Site:
    surface: Surface
    cej: Optional[Pt] = None
    cej2: Optional[Pt] = None       # 釉牙骨质界下 2mm，③④公式的起点
    ac: Optional[Pt] = None
    apex: Optional[Pt] = None
    skipped: bool = False       # 该侧被邻牙遮挡看不清 → 跳过，不参与取大
    point_meta: dict = field(default_factory=dict)
    image_side: Optional[str] = None
    side_confirmed: bool = True   # legacy manual sites already have an anatomical label

    @property
    def display_label(self) -> str:
        if not self.side_confirmed:
            side = {"image_left": "图像左", "image_right": "图像右"}.get(self.image_side, "候选侧")
            return side + "（待确认）"
        return SURFACE_LABEL.get(self.surface, self.surface)

    # ── 点访问 ───────────────────────────────────────────────────
    def get(self, role: str) -> Optional[Pt]:
        return getattr(self, role)

    def set(self, role: str, pt: Optional[Pt]) -> None:
        if role not in ROLES:
            raise ValueError("未知点位类型")
        previous = self.get(role)
        if previous == pt:
            return
        info = self.point_meta.setdefault(role, {"origin": "manual", "raw_xy": None,
                                                "edited": False, "history": []})
        info.setdefault("history", []).append({"previous_xy": list(previous.as_tuple()) if previous else None,
                                "current_xy": list(pt.as_tuple()) if pt else None,
                                "at": datetime.now(timezone.utc).isoformat(timespec="milliseconds")})
        info["edited"] = info.get("origin") == "model" or info.get("edited", False)
        info["review_status"] = "reviewed" if pt else "rejected"
        setattr(self, role, pt)

    def has(self, roles) -> bool:
        return all(self.get(r) is not None for r in roles)

    @property
    def complete(self) -> bool:
        """4 个点全齐 —— 此时四个公式都能算。"""
        return self.has(ROLES)

    def usable(self, fml: F.Formula) -> bool:
        """**该公式**所需的点是否齐全。

        只标了 CEJ/AC/根尖 的旧数据，用①②公式照样能算，用③④才缺 P2。
        所以「完成」是相对于公式而言的，不是一刀切的 4 点。
        """
        return not self.skipped and self.has(fml.needs)

    @property
    def filled_count(self) -> int:
        return sum(1 for r in ROLES if self.get(r) is not None)

    def points_map(self) -> dict[str, g.Vec | None]:
        return {r: (p.as_tuple() if (p := self.get(r)) else None) for r in ROLES}

    # ── 计算（派生量，不持久化） ────────────────────────────────────
    def metrics(self, fml: F.Formula, cfg: F.FormulaConfig) -> Optional[F.Metrics]:
        """按给定公式算。缺该公式需要的点时返回 None（由 Formula 自己判定）。"""
        if self.skipped:
            return None
        try:
            return fml(self.points_map(), cfg)
        except F.FormulaError:
            return None

    # ── 序列化 ───────────────────────────────────────────────────
    def to_dict(self, tooth_index: int) -> dict:
        d: dict = {"surface": self.surface, "skipped": self.skipped,
                   "image_side": self.image_side, "side_confirmed": self.side_confirmed,
                   "surface_semantics": "anatomical" if self.side_confirmed else "unconfirmed_slot",
                   "point_meta": copy.deepcopy(self.point_meta)}
        for r in ROLES:
            p = self.get(r)
            d[r] = p.to_dict(point_label(tooth_index, self.surface, r)) if p else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Site":
        return cls(
            surface=d.get("surface", "mesial"),
            cej=Pt.from_dict(d.get("cej")),
            cej2=Pt.from_dict(d.get("cej2")),
            ac=Pt.from_dict(d.get("ac")),
            apex=Pt.from_dict(d.get("apex")),
            skipped=bool(d.get("skipped", False)),
            point_meta=copy.deepcopy(d.get("point_meta", {})),
            image_side=d.get("image_side"),
            side_confirmed=bool(d.get("side_confirmed", True)),
        )


# ── 牙 ──────────────────────────────────────────────────────────────────


@dataclass
class Tooth:
    fdi: Optional[int] = None                       # 牙位号，如 16；None = 未指定
    index: int = 0                                  # 本片中的第几颗（决定 P 编号与颜色）
    roi: Optional[tuple[float, float, float, float]] = None   # x, y, w, h
    sites: list[Site] = field(default_factory=lambda: [Site("mesial"), Site("distal")])
    tooth_id: str = field(default_factory=lambda: uuid4().hex)
    origin: str = "manual"
    segmentation: dict = field(default_factory=dict)
    candidate_surfaces: list[dict] = field(default_factory=list)
    initial_auto_roi: Optional[tuple[float, float, float, float]] = None

    @property
    def roi_corners(self) -> dict[str, list[float]]:
        """Clockwise rectangle corners in original image pixels, always following roi."""
        if self.roi is None:
            return {}
        x, y, w, h = self.roi
        return {"top_left": [x, y], "top_right": [x+w, y],
                "bottom_right": [x+w, y+h], "bottom_left": [x, y+h]}

    @property
    def color(self) -> str:
        return TOOTH_COLORS[self.index % len(TOOTH_COLORS)]

    @property
    def name(self) -> str:
        return str(self.fdi) if self.fdi else f"#{self.index + 1}"

    def site(self, surface: Surface) -> Site:
        for s in self.sites:
            if s.surface == surface:
                return s
        s = Site(surface)
        self.sites.append(s)
        return s

    @property
    def complete(self) -> bool:
        """严格：两侧都已处理，且至少有一侧 4 个点全齐。"""
        done = [s.complete or s.skipped for s in self.sites]
        return all(done) and any(s.complete for s in self.sites)

    def complete_for(self, fml: F.Formula) -> bool:
        """按**当前公式**判定是否标完 —— 用①②只需 3 点，用③④才需要 4 点。"""
        states = [(s.usable(fml), s.skipped) for s in self.sites]
        return all(u or k for u, k in states) and any(u for u, _ in states)

    @property
    def filled_count(self) -> int:
        return sum(s.filled_count for s in self.sites)

    def worst(self, fml: F.Formula, cfg: F.FormulaConfig) -> tuple[Optional[Site], Optional[F.Metrics]]:
        """本牙近远中里比值较大的那一侧。"""
        best_site, best_m = None, None
        for s in self.sites:
            m = s.metrics(fml, cfg)
            if m is None or not m.valid:
                continue
            if best_m is None or m.ratio > best_m.ratio:
                best_site, best_m = s, m
        return best_site, best_m

    def to_dict(self) -> dict:
        return {
            "fdi": self.fdi,
            "index": self.index,
            "color": self.color,
            "roi": list(self.roi) if self.roi else None,
            "roi_corners": self.roi_corners,
            "roi_coordinate_space": "image_pixels",
            "sites": [s.to_dict(self.index) for s in self.sites],
            "tooth_id": self.tooth_id, "origin": self.origin,
            "segmentation": copy.deepcopy(self.segmentation),
            "candidate_surfaces": copy.deepcopy(self.candidate_surfaces),
            "initial_auto_roi": list(self.initial_auto_roi) if self.initial_auto_roi else None,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Tooth":
        roi = d.get("roi")
        sites = [Site.from_dict(s) for s in d.get("sites", [])]
        have = {s.surface for s in sites}
        for sf in SURFACES:                     # 补齐缺失的一侧，保证 UI 结构稳定
            if sf not in have:
                sites.append(Site(sf))
        sites.sort(key=lambda s: SURFACES.index(s.surface))
        return cls(
            fdi=d.get("fdi"),
            index=int(d.get("index", 0)),
            roi=tuple(roi) if roi else None,
            sites=sites,
            tooth_id=d.get("tooth_id") or uuid4().hex,
            origin=d.get("origin", "manual"),
            segmentation=copy.deepcopy(d.get("segmentation", {})),
            candidate_surfaces=copy.deepcopy(d.get("candidate_surfaces", [])),
            initial_auto_roi=tuple(d["initial_auto_roi"]) if d.get("initial_auto_roi") else None,
        )


# ── 病例（一张全景片） ────────────────────────────────────────────────────


@dataclass
class Patient:
    id: str = ""
    age: Optional[float] = None
    sex: str = ""
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "age": self.age,
            "sex": self.sex,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Patient":
        age = d.get("age")
        return cls(
            id=str(d.get("id", "")),
            age=float(age) if age not in (None, "") else None,
            sex=str(d.get("sex", "")),
            note=str(d.get("note", "")),
        )


@dataclass
class CrestCurve:
    """牙槽嵴顶曲线 —— ⛔ 功能已停用，此字段仅为兼容既有标注文件而保留。

    旧的 annotations/*.json 里可能存着曲线点，读进来不报错、也不再显示或使用。
    """

    upper: list[tuple[int, int]] = field(default_factory=list)
    lower: list[tuple[int, int]] = field(default_factory=list)
    generated: bool = False

    def to_dict(self) -> dict:
        return {
            "generated": self.generated,
            "upper": [[int(x), int(y)] for x, y in self.upper],
            "lower": [[int(x), int(y)] for x, y in self.lower],
        }

    @classmethod
    def from_dict(cls, d: dict | None) -> "CrestCurve":
        if not d:
            return cls()
        return cls(
            upper=[(int(x), int(y)) for x, y in d.get("upper", [])],
            lower=[(int(x), int(y)) for x, y in d.get("lower", [])],
            generated=bool(d.get("generated", False)),
        )


@dataclass
class CaseResult:
    """一次计算的完整结果。纯派生量，不写盘。

    只给事实（比例、年龄比、所属影像学区间），**不下分期分级结论** ——
    Stage/Grade 需要结合缺牙数、探诊、病史等临床资料，全景片给不了。
    """

    worst_ratio: Optional[float] = None
    worst_tooth: Optional[Tooth] = None
    worst_site: Optional[Site] = None
    worst_metrics: Optional[F.Metrics] = None
    bone_loss_age_ratio: Optional[float] = None
    interval: Optional[str] = None          # "I" / "II" / "III"，2018 影像学骨吸收区间


SCHEMA_VERSION = 5     # v5: persisted rectangle undo and initial automatic rectangle


@dataclass
class CaseAnnotation:
    image_file: str = ""
    image_width: int = 0
    image_height: int = 0
    image_sha1: str = ""
    patient: Patient = field(default_factory=Patient)
    formula_id: str = F.DEFAULT_FORMULA_ID
    teeth: list[Tooth] = field(default_factory=list)
    crest: CrestCurve = field(default_factory=CrestCurve)
    created: str = ""
    updated: str = ""
    duration_s: float = 0.0
    status: str = "pending"          # pending / in_progress / done / flagged
    ai_runs: list[dict] = field(default_factory=list)
    box_history: list[dict] = field(default_factory=list)

    # ── 牙管理 ───────────────────────────────────────────────────
    def add_tooth(self, fdi: Optional[int] = None,
                  roi: Optional[tuple[float, float, float, float]] = None) -> Tooth:
        t = Tooth(fdi=fdi, index=len(self.teeth), roi=roi)
        self.teeth.append(t)
        return t

    def remove_tooth(self, tooth: Tooth) -> None:
        if tooth in self.teeth:
            self.teeth.remove(tooth)
            self.reindex()

    def reindex(self) -> None:
        """删牙后重排 index —— P 编号和颜色随之连续。"""
        for i, t in enumerate(self.teeth):
            t.index = i

    @property
    def annotated_tooth_count(self) -> int:
        """按当前公式算「标完了几颗牙」。切到需要 P2 的③④公式后，
        只标了 3 点的牙会如实变回未完成 —— 这正是需要的提示。"""
        fml = F.get(self.formula_id)
        return sum(1 for t in self.teeth if t.complete_for(fml))

    # ── 计算（派生量） ────────────────────────────────────────────
    def compute(self, cfg: GradingConfig) -> CaseResult:
        fml = F.get(self.formula_id)
        fcfg = cfg.formula_config()
        res = CaseResult()
        for t in self.teeth:
            s, m = t.worst(fml, fcfg)
            if m is None:
                continue
            if res.worst_metrics is None or m.ratio > res.worst_metrics.ratio:
                res.worst_tooth, res.worst_site, res.worst_metrics = t, s, m
        if res.worst_metrics is not None:
            res.worst_ratio = res.worst_metrics.ratio
            if self.patient.age:
                res.bone_loss_age_ratio = res.worst_ratio / self.patient.age
        res.interval = interval_of(res.worst_ratio, cfg)
        return res

    def all_metrics(self, cfg: GradingConfig) -> list[tuple[Tooth, Site, Optional[F.Metrics]]]:
        """按牙序 / 近中远中顺序列出所有位点及其结果，供表格与导出使用。"""
        fml = F.get(self.formula_id)
        fcfg = cfg.formula_config()
        rows = []
        for t in self.teeth:
            for sf in SURFACES:
                s = t.site(sf)
                rows.append((t, s, s.metrics(fml, fcfg)))
        return rows

    # ── 序列化 ───────────────────────────────────────────────────
    def touch(self) -> None:
        self.updated = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        if not self.created:
            self.created = self.updated

    def to_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "image": {
                "file": self.image_file,
                "width": self.image_width,
                "height": self.image_height,
                "sha1": self.image_sha1,
            },
            "patient": self.patient.to_dict(),
            "formula": {"id": self.formula_id},
            "teeth": [t.to_dict() for t in self.teeth],
            "bone_crest_curve": self.crest.to_dict(),
            "ai_runs": copy.deepcopy(self.ai_runs),
            "box_history": copy.deepcopy(self.box_history),
            "meta": {
                "created": self.created,
                "updated": self.updated,
                "duration_s": round(self.duration_s, 1),
                "status": self.status,
            },
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CaseAnnotation":
        img = d.get("image", {})
        meta = d.get("meta", {})
        teeth = [Tooth.from_dict(t) for t in d.get("teeth", [])]
        for i, t in enumerate(teeth):       # index 以文件顺序为准，防止旧数据错位
            t.index = i
        return cls(
            image_file=img.get("file", ""),
            image_width=int(img.get("width", 0)),
            image_height=int(img.get("height", 0)),
            image_sha1=img.get("sha1", ""),
            patient=Patient.from_dict(d.get("patient", {})),
            formula_id=(d.get("formula") or {}).get("id", F.DEFAULT_FORMULA_ID),
            teeth=teeth,
            crest=CrestCurve.from_dict(d.get("bone_crest_curve")),
            created=meta.get("created", ""),
            updated=meta.get("updated", ""),
            duration_s=float(meta.get("duration_s", 0) or 0),
            status=meta.get("status", "pending"),
            ai_runs=copy.deepcopy(d.get("ai_runs", [])),
            box_history=copy.deepcopy(d.get("box_history", [])),
        )
