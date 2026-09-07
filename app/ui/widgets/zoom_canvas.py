"""可缩放/平移的图像画布。全景片视图与单牙放大视图共用这一个基类。

交互（与 labelme 等标注工具的习惯一致）：
  · 滚轮            以光标为锚点缩放
  · 中键拖 / 空格拖 / 触控板双指   平移
  · 抓手工具       左键空白处拖动平移，点上仍可拖点
  · 双击            适配窗口
  · 左键            发出 clicked 信号（携带图像坐标）

设计参考 marcel-goldschen-ohm/PyQtImageViewer（MIT）的思路，代码为本项目重写。
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
    QWidget,
)

from .imageutil import gray_to_qpixmap

MIN_SCALE = 0.02
MAX_SCALE = 60.0


class ZoomCanvas(QGraphicsView):
    clicked = Signal(QPointF)            # 左键单击，图像坐标
    moved = Signal(QPointF)              # 鼠标移动，图像坐标（状态栏显示用）
    zoom_changed = Signal(float)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pix_item: QGraphicsPixmapItem | None = None
        self._panning = False
        self._pan_origin = QPointF()
        self._space_held = False
        self._hand_tool = False
        self._pan_button = Qt.MouseButton.NoButton
        # 首次适配窗口是否还欠着。widget 还没布局完时 viewport 尺寸是无效的，
        # 这时 fitInView 会把图缩成一小团；所以记账，等真正拿到尺寸再补一次。
        self._fit_pending = False
        self._pending_fit_rect: QRectF | None = None

        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setBackgroundBrush(QBrush(QColor("#121417")))
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    # ── 图像 ─────────────────────────────────────────────────────
    def set_image(self, arr: np.ndarray | None, keep_view: bool = False) -> None:
        pix = gray_to_qpixmap(arr) if arr is not None else QPixmap()
        transform = self.transform() if keep_view else None
        center = self.mapToScene(self.viewport().rect().center()) if keep_view else None

        if self._pix_item is None:
            self._pix_item = self._scene.addPixmap(pix)
            self._pix_item.setZValue(-100)
        else:
            self._pix_item.setPixmap(pix)

        self._scene.setSceneRect(QRectF(pix.rect()))
        self._update_pan_extent()
        if keep_view and transform is not None:
            self.setTransform(transform)
            self.centerOn(center)
        else:
            self.fit()

    @property
    def has_image(self) -> bool:
        return self._pix_item is not None and not self._pix_item.pixmap().isNull()

    def image_size(self) -> tuple[int, int]:
        if not self.has_image:
            return (0, 0)
        p = self._pix_item.pixmap()
        return (p.width(), p.height())

    # ── 缩放 ─────────────────────────────────────────────────────
    def current_scale(self) -> float:
        return float(self.transform().m11())

    def fit(self, rect: QRectF | None = None) -> None:
        """适配窗口。rect 为空时用整幅图。

        widget 还没布局完（viewport 退化成 ~100x30）时先记账，
        等 showEvent / resizeEvent 拿到真实尺寸再自动补一次。
        """
        if not self.has_image:
            return
        target = rect if rect is not None else self._scene.sceneRect()
        self._pending_fit_rect = target
        vp = self.viewport().size()
        if vp.width() < 50 or vp.height() < 50:
            self._fit_pending = True
            return
        self._fit_pending = False
        self.fitInView(target, Qt.AspectRatioMode.KeepAspectRatio)
        self._update_pan_extent()
        self.zoom_changed.emit(self.current_scale())

    def _update_pan_extent(self) -> None:
        """Leave room around the image to pan even at 'fit image'.

        The view's scroll area can exceed the image. The underlying scene rectangle
        remains the true image bounds so dragging points still clamps correctly.
        """
        if not self.has_image:
            self.setSceneRect(QRectF())
            return
        inverse, _ = self.viewportTransform().inverted()
        center = inverse.map(QPointF(self.viewport().width() / 2,
                                    self.viewport().height() / 2))
        image = self._scene.sceneRect()
        scale = max(self.current_scale(), MIN_SCALE)
        margin_x = max(image.width(), self.viewport().width() / scale)
        margin_y = max(image.height(), self.viewport().height() / scale)
        extent = image.adjusted(-margin_x, -margin_y, margin_x, margin_y)
        extent = extent.united(QRectF(center.x()-margin_x, center.y()-margin_y,
                                     margin_x*2, margin_y*2))
        self.setSceneRect(extent)
        self.centerOn(center)

    def _flush_pending_fit(self) -> None:
        if self._fit_pending and self._pending_fit_rect is not None:
            self.fit(self._pending_fit_rect)

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self._flush_pending_fit()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._update_pan_extent()
        self._flush_pending_fit()

    def zoom_by(self, factor: float) -> None:
        s = self.current_scale()
        target = max(MIN_SCALE, min(MAX_SCALE, s * factor))
        if abs(target - s) < 1e-9:
            return
        self._fit_pending = False          # 用户主动缩放了，别再自动纠正
        self.scale(target / s, target / s)
        self._update_pan_extent()
        self.zoom_changed.emit(self.current_scale())

    def zoom_to(self, scale: float) -> None:
        s = self.current_scale()
        if s > 0:
            self.zoom_by(scale / s)

    def wheelEvent(self, e: QWheelEvent) -> None:
        if not self.has_image:
            return
        pixels = e.pixelDelta()
        if not pixels.isNull():
            self.pan_by_pixels(QPointF(pixels))
            e.accept()
            return
        if e.angleDelta().x():
            self.pan_by_pixels(QPointF(e.angleDelta().x() / 2, 0))
            e.accept()
            return
        delta = e.angleDelta().y()
        if delta == 0:
            return
        self.zoom_by(1.18 if delta > 0 else 1 / 1.18)
        e.accept()

    # ── 平移 ─────────────────────────────────────────────────────
    def set_hand_tool(self, on: bool) -> None:
        self._hand_tool = bool(on)
        self._update_cursor()

    def _movable_item_at(self, position) -> bool:
        item = self.itemAt(position.toPoint())
        while item is not None:
            if item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable:
                return True
            item = item.parentItem()
        return False

    def _update_cursor(self) -> None:
        self.setCursor(Qt.CursorShape.ClosedHandCursor if self._panning else
                       Qt.CursorShape.OpenHandCursor if self._hand_tool or self._space_held else
                       Qt.CursorShape.ArrowCursor)

    def _pan_active(self, e) -> bool:
        return (
            e.button() == Qt.MouseButton.MiddleButton
            or (e.button() == Qt.MouseButton.LeftButton and self._space_held)
            or (e.button() == Qt.MouseButton.LeftButton
                and e.modifiers() & Qt.KeyboardModifier.ControlModifier)
            or (e.button() == Qt.MouseButton.LeftButton and self._hand_tool
                and not self._movable_item_at(e.position()))
        )

    def pan_by_pixels(self, delta: QPointF) -> None:
        if not self.has_image:
            return
        self._fit_pending = False
        self._update_pan_extent()
        h, v = self.horizontalScrollBar(), self.verticalScrollBar()
        h.setValue(h.value() - round(delta.x()))
        v.setValue(v.value() - round(delta.y()))

    def mousePressEvent(self, e) -> None:
        if self.has_image and self._pan_active(e):
            self._panning = True
            self._pan_button = e.button()
            self._pan_origin = e.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            e.accept()
            return
        super().mousePressEvent(e)
        if e.button() == Qt.MouseButton.LeftButton and self.has_image and not e.isAccepted():
            pass    # 交给子类的 on_canvas_click

    def mouseMoveEvent(self, e) -> None:
        if self._panning:
            d = e.position() - self._pan_origin
            self._pan_origin = e.position()
            self.pan_by_pixels(d)
            e.accept()
            return
        if self.has_image:
            self.moved.emit(self.mapToScene(e.position().toPoint()))
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        if self._panning and e.button() == self._pan_button:
            self._panning = False
            self._pan_button = Qt.MouseButton.NoButton
            self._update_cursor()
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.fit()
            e.accept()
            return
        super().mouseDoubleClickEvent(e)

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Space and not e.isAutoRepeat():
            self._space_held = True
            self._update_cursor()
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Space and not e.isAutoRepeat():
            self._space_held = False
            if not self._panning:
                self._update_cursor()
        super().keyReleaseEvent(e)

    # ── 便利 ─────────────────────────────────────────────────────
    def scene_(self) -> QGraphicsScene:
        return self._scene

    def clear_overlay(self, keep_pixmap: bool = True) -> None:
        for item in list(self._scene.items()):
            if keep_pixmap and item is self._pix_item:
                continue
            self._scene.removeItem(item)
