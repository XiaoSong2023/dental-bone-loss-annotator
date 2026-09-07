"""可拖拽的标定点。

关键点：用 ItemIgnoresTransformations 让点的**屏幕尺寸恒定** ——
放大到 20 倍时点还是那么大，不会糊成一片，这对精细标定至关重要。
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject

RADIUS = 5.0          # 屏幕像素
HIT_PAD = 6.0
CROSS = 11.0


class PointItem(QGraphicsObject):
    moved = Signal(object, QPointF)          # (self, 新的图像坐标)
    move_finished = Signal(object)
    picked = Signal(object)

    def __init__(self, pos: QPointF, color: str, label: str,
                 role_short: str = "", movable: bool = True):
        super().__init__()
        self._color = QColor(color)
        self._label = label
        self._role = role_short
        self._hover = False
        self._active = False

        self.setPos(pos)
        self.setZValue(100)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, movable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, movable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges, True)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.SizeAllCursor if movable else Qt.CursorShape.ArrowCursor)
        self.setToolTip(f"{label} · {role_short}" if role_short else label)

    # ── 外观 ─────────────────────────────────────────────────────
    def set_active(self, on: bool) -> None:
        if self._active != on:
            self._active = on
            self.update()

    def set_label(self, label: str) -> None:
        self._label = label
        self.update()

    def boundingRect(self) -> QRectF:
        # 要容下右下角的文字标签
        return QRectF(-CROSS - HIT_PAD, -CROSS - HIT_PAD,
                      2 * (CROSS + HIT_PAD) + 62, 2 * (CROSS + HIT_PAD) + 14)

    def shape(self):
        from PySide6.QtGui import QPainterPath
        p = QPainterPath()
        r = RADIUS + HIT_PAD
        p.addEllipse(QPointF(0, 0), r, r)
        return p

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        c = QColor(self._color)

        # 十字丝：在高对比度的 X 光片上比单纯的点更容易对准
        pen = QPen(QColor(0, 0, 0, 170), 3.0)
        painter.setPen(pen)
        painter.drawLine(QPointF(-CROSS, 0), QPointF(CROSS, 0))
        painter.drawLine(QPointF(0, -CROSS), QPointF(0, CROSS))
        painter.setPen(QPen(c, 1.4))
        painter.drawLine(QPointF(-CROSS, 0), QPointF(CROSS, 0))
        painter.drawLine(QPointF(0, -CROSS), QPointF(0, CROSS))

        r = RADIUS + (2.0 if (self._hover or self._active) else 0.0)
        painter.setPen(QPen(QColor(0, 0, 0, 200), 2.4))
        painter.drawEllipse(QPointF(0, 0), r, r)
        painter.setPen(QPen(c, 1.8))
        painter.setBrush(QBrush(QColor(c.red(), c.green(), c.blue(), 90)))
        painter.drawEllipse(QPointF(0, 0), r, r)

        if self._active:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#FFFFFF"), 1.2, Qt.PenStyle.DashLine))
            painter.drawEllipse(QPointF(0, 0), r + 5, r + 5)

        if self._label:
            f = QFont()
            f.setPointSizeF(8.5)
            f.setBold(True)
            painter.setFont(f)
            tp = QPointF(CROSS + 3, -CROSS + 2)
            painter.setPen(QPen(QColor(0, 0, 0, 210), 3.0))
            painter.drawText(tp, self._label)
            painter.setPen(QPen(c))
            painter.drawText(tp, self._label)

    # ── 交互 ─────────────────────────────────────────────────────
    def hoverEnterEvent(self, e):
        self._hover = True
        self.update()
        super().hoverEnterEvent(e)

    def hoverLeaveEvent(self, e):
        self._hover = False
        self.update()
        super().hoverLeaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.picked.emit(self)
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        if e.button() == Qt.MouseButton.LeftButton:
            self.move_finished.emit(self)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemScenePositionHasChanged:
            self.moved.emit(self, self.scenePos())
        return super().itemChange(change, value)
