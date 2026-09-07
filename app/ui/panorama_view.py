"""主画布 —— 画框选牙 + 标注回显。全景片与根尖片共用。

两种模式：
  · 浏览模式：看已标的点，拖动点微调
  · 画框选牙：拖出方框把可疑牙位框住，框由医生画，
    所以「牙冠 + 牙根 + 根尖必须完整」由医生直接保证，软件不做猜测

所有在单牙放大图上标的点，都会自动映射回这里的原图坐标显示，
不同牙用不同颜色，标签按 P(8n−7)…P(8n) 规则（每颗牙 8 个点）。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPen
from PySide6.QtWidgets import QGraphicsItem

from ..core import geometry as g
from ..core.formula import Formula, FormulaConfig
from ..core.models import (
    ROLES,
    ROLE_SHORT,
    CaseAnnotation,
    Tooth,
    point_label,
)
from . import theme as T
from .widgets.point_item import PointItem
from .widgets.zoom_canvas import ZoomCanvas

MODE_VIEW = "view"
MODE_PICK = "pick"       # 拖框选牙


@dataclass
class Layers:
    points: bool = True
    labels: bool = True
    axis: bool = True
    roi: bool = True


MIN_BOX = 18.0          # 小于这个尺寸的拖拽当成误触，不成框


class PanoramaView(ZoomCanvas):
    box_drawn = Signal(QRectF)              # 画框选牙：拖出一个框
    point_dragged = Signal(object, object, str, QPointF)   # tooth, site, role, 新坐标

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode = MODE_VIEW
        self.layers = Layers()
        self._ann: CaseAnnotation | None = None
        self._formula: Formula | None = None
        self._fcfg = FormulaConfig()
        self._overlay: list[QGraphicsItem] = []
        self._gray: np.ndarray | None = None
        self._rubber = None                 # 正在拖拽的选框
        self._rubber_origin: QPointF | None = None

    # ── 数据 ─────────────────────────────────────────────────────
    def set_case(self, gray: np.ndarray | None, ann: CaseAnnotation | None,
                 formula: Formula | None = None, fcfg: FormulaConfig | None = None,
                 keep_view: bool = False) -> None:
        self._gray = gray
        self._ann = ann
        if formula is not None:
            self._formula = formula
        if fcfg is not None:
            self._fcfg = fcfg
        self.set_image(gray, keep_view=keep_view)
        self.refresh_overlay()

    def set_display_image(self, gray: np.ndarray) -> None:
        """只换显示用的增强图，不动标注与视野。"""
        self._gray = gray
        self.set_image(gray, keep_view=True)
        self.refresh_overlay()

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.setCursor(
            Qt.CursorShape.CrossCursor if mode == MODE_PICK
            else Qt.CursorShape.ArrowCursor
        )

    # ── 叠加层 ────────────────────────────────────────────────────
    def refresh_overlay(self) -> None:
        for it in self._overlay:
            if it.scene() is self.scene_():
                self.scene_().removeItem(it)
        self._overlay.clear()
        if self._ann is None:
            return
        self._draw_teeth()

    def _add(self, item: QGraphicsItem) -> QGraphicsItem:
        self.scene_().addItem(item)
        self._overlay.append(item)
        return item

    def _draw_teeth(self) -> None:
        for tooth in self._ann.teeth:
            color = QColor(tooth.color)
            if self.layers.roi and tooth.roi:
                x, y, w, h = tooth.roi
                pen = QPen(color, 1.6, Qt.PenStyle.DashLine)
                pen.setCosmetic(True)
                pen.setDashPattern([6, 4])
                rect = self.scene_().addRect(QRectF(x, y, w, h), pen)
                rect.setZValue(5)
                rect.setOpacity(0.85 if not tooth.complete else 0.45)
                self._overlay.append(rect)

            for site in tooth.sites:
                if site.skipped:
                    continue
                if self.layers.axis:
                    self._draw_axis(tooth, site, color)
                if self.layers.points:
                    for role in ROLES:
                        p = site.get(role)
                        if p is None:
                            continue
                        item = PointItem(
                            QPointF(p.x, p.y),
                            tooth.color,
                            point_label(tooth.index, site.surface, role) if self.layers.labels else "",
                            ROLE_SHORT[role],
                            movable=True,
                        )
                        item.moved.connect(
                            lambda _it, pos, t=tooth, s=site, r=role:
                            self.point_dragged.emit(t, s, r, pos)
                        )
                        item.move_finished.connect(
                            lambda _it: QTimer.singleShot(0, self, self.refresh_overlay)
                        )
                        self._add(item)

            if self.layers.labels:
                self._draw_tooth_caption(tooth, color)

    def _draw_axis(self, tooth: Tooth, site, color: QColor) -> None:
        """画长轴与投影关系。

        起点跟着**当前公式**走：①②从 CEJ 起，③④从 CEJ 下 2mm 起。
        这样切换公式时画面上的长轴会立刻跟着变，所见即所算。
        """
        needs = self._formula.needs if self._formula is not None else ("cej",)
        origin_role = "cej2" if "cej2" in needs else "cej"
        origin, ac, apex = site.get(origin_role), site.ac, site.apex
        if origin is None or apex is None:
            return
        pen = QPen(color, 1.1, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        pen.setDashPattern([5, 4])
        line = self.scene_().addLine(QLineF(origin.x, origin.y, apex.x, apex.y), pen)
        line.setZValue(8)
        line.setOpacity(0.8)
        self._overlay.append(line)

        if ac is None:
            return
        # AC 到长轴的垂足 —— 把「投影」这件事画出来，肉眼可验证
        foot = g.foot_of_perpendicular(ac.as_tuple(), origin.as_tuple(), apex.as_tuple())
        pen2 = QPen(color, 1.0, Qt.PenStyle.DotLine)
        pen2.setCosmetic(True)
        drop = self.scene_().addLine(QLineF(ac.x, ac.y, foot[0], foot[1]), pen2)
        drop.setZValue(8)
        drop.setOpacity(0.9)
        self._overlay.append(drop)

        # 骨吸收段（起点 → 垂足）用粗实线强调
        pen3 = QPen(color, 3.0)
        pen3.setCosmetic(True)
        seg = self.scene_().addLine(QLineF(origin.x, origin.y, foot[0], foot[1]), pen3)
        seg.setZValue(7)
        seg.setOpacity(0.55)
        self._overlay.append(seg)

    def _draw_tooth_caption(self, tooth: Tooth, color: QColor) -> None:
        # 挂在 ROI 框的左上角，避开点位标签；没有框时退回到第一个 CEJ
        if tooth.roi:
            ax, ay = tooth.roi[0], tooth.roi[1]
        else:
            anchor = next((s.cej for s in tooth.sites if s.cej is not None), None)
            if anchor is None:
                return
            ax, ay = anchor.x, anchor.y

        parts = [tooth.name]
        if self._formula is not None:
            vals = []
            for site in tooth.sites:
                if site.skipped:
                    vals.append("跳过")
                    continue
                m = site.metrics(self._formula, self._fcfg)
                vals.append("—" if m is None else f"{m.ratio:.2f}")
            parts.append("/".join(vals))
        text = "  ".join(parts)

        item = self.scene_().addText("")
        item.setHtml(
            f'<div style="background:#12161c;color:{color.name()};'
            f'font-weight:700;">&nbsp;{text}&nbsp;</div>'
        )
        f = QFont()
        f.setPointSizeF(9.0)
        f.setBold(True)
        item.setFont(f)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        item.setPos(ax, ay)
        item.setOpacity(0.95)
        item.setZValue(120)
        self._overlay.append(item)

    # ── 画框选牙 ──────────────────────────────────────────────────
    def _clamp(self, p: QPointF) -> QPointF:
        w, h = self.image_size()
        return QPointF(max(0.0, min(p.x(), w - 1)), max(0.0, min(p.y(), h - 1)))

    def mousePressEvent(self, e) -> None:
        if (
            self.mode == MODE_PICK
            and e.button() == Qt.MouseButton.LeftButton
            and not (e.modifiers() & Qt.KeyboardModifier.ControlModifier)
            and self.has_image
        ):
            self._rubber_origin = self._clamp(self.mapToScene(e.position().toPoint()))
            color = QColor(T.BOX_DRAW)
            pen = QPen(color, 1.8, Qt.PenStyle.SolidLine)
            pen.setCosmetic(True)
            fill = QColor(color)
            fill.setAlpha(38)
            self._rubber = self.scene_().addRect(
                QRectF(self._rubber_origin, self._rubber_origin), pen, QBrush(fill)
            )
            self._rubber.setZValue(200)
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e) -> None:
        if self._rubber is not None and self._rubber_origin is not None:
            cur = self._clamp(self.mapToScene(e.position().toPoint()))
            self._rubber.setRect(QRectF(self._rubber_origin, cur).normalized())
            self.moved.emit(cur)
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        if self._rubber is not None and e.button() == Qt.MouseButton.LeftButton:
            rect = self._rubber.rect().normalized()
            self.cancel_box()
            e.accept()
            if rect.width() >= MIN_BOX and rect.height() >= MIN_BOX:
                self.box_drawn.emit(rect)
            return
        super().mouseReleaseEvent(e)

    def cancel_box(self) -> None:
        if self._rubber is not None and self._rubber.scene() is self.scene_():
            self.scene_().removeItem(self._rubber)
        self._rubber = None
        self._rubber_origin = None

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Escape:
            self.cancel_box()
        super().keyPressEvent(e)
