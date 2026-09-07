"""分步放大标定对话框 —— 软件的核心交互。

流程：选定 2–3 颗牙后逐颗放大，每颗按解剖顺序（由咬合面向根尖）标 8 个点：
    近中 P1 CEJ → P2 CEJ下2mm → P3 牙槽嵴顶 → P4 根尖
    远中 P5 CEJ → P6 CEJ下2mm → P7 牙槽嵴顶 → P8 根尖
两侧四点标完或明确跳过后自动下一颗，最后一颗停留，点「完成标定」。

步骤表是从 models.ROLES × SURFACES 自动派生的，将来再加点位不用改这里。

设计要点：画布里放的是**完整片子**，只是初始视野缩放到该牙的 ROI。
这样根尖永远不会被裁掉（你明确要求「不能残缺」），坐标也天然就是原图坐标，
不需要任何 ROI ↔ 原图的坐标换算，少一整类 bug。
"""

from __future__ import annotations

from copy import deepcopy

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..core import geometry as g
from ..core.formula import Formula, FormulaConfig
from ..core.models import (
    ROLE_LABEL,
    ROLE_SHORT,
    ROLES,
    SURFACE_LABEL,
    SURFACES,
    CaseAnnotation,
    Pt,
    Site,
    Tooth,
    point_label,
)
from . import theme as T
from .panorama_view import Layers, PanoramaView

# 8 个步骤：一侧的 4 个点走完，再走另一侧
STEPS: list[tuple[str, str]] = [(sf, r) for sf in SURFACES for r in ROLES]


class AnnotateCanvas(PanoramaView):
    """标定画布：空白处左键 = 落点；点上左键 = 拖动。"""

    canvas_clicked = Signal(QPointF)

    def mousePressEvent(self, e) -> None:
        from .widgets.zoom_canvas import ZoomCanvas
        if self._pan_active(e):
            ZoomCanvas.mousePressEvent(self, e)
            return
        if (
            e.button() == Qt.MouseButton.LeftButton
            and not (e.modifiers() & Qt.KeyboardModifier.ControlModifier)
            and self.has_image
        ):
            item = self.itemAt(e.position().toPoint())
            on_point = item is not None and item.__class__.__name__ == "PointItem"
            if not on_point:
                pos = self.mapToScene(e.position().toPoint())
                w, h = self.image_size()
                if 0 <= pos.x() < w and 0 <= pos.y() < h:
                    self.canvas_clicked.emit(pos)
                    e.accept()
                    return
        # 绕开 PanoramaView 的选牙逻辑
        ZoomCanvas.mousePressEvent(self, e)

    def mouseDoubleClickEvent(self, e) -> None:
        # The review dialog already has a selected tooth; do not open a second chooser.
        from .widgets.zoom_canvas import ZoomCanvas
        ZoomCanvas.mouseDoubleClickEvent(self, e)


class ToothDialog(QDialog):
    def __init__(self, gray: np.ndarray, ann: CaseAnnotation, teeth: list[Tooth],
                 formula: Formula, fcfg: FormulaConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("分步放大标定")
        self.setModal(True)
        self.resize(1180, 820)

        self._gray = gray
        self._original_ann = ann
        self._ann = deepcopy(ann)
        self._teeth = [self._ann.teeth[ann.teeth.index(t)] for t in teeth]
        self._formula = formula
        self._fcfg = fcfg
        self._ti = 0                      # 当前第几颗牙
        self._si = 0                      # 当前第几步（0–7）
        self._undo: list[tuple[Tooth, str, str, Pt | None]] = []

        self._build_ui()
        self._install_shortcuts()
        self._goto_tooth(0)

    def accept(self) -> None:
        # Editing is transactional: Esc/Cancel never alters saved or AI raw points.
        self._original_ann.teeth = deepcopy(self._ann.teeth)
        super().accept()

    # ── 界面 ─────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        self.canvas = AnnotateCanvas(self)
        self.canvas.layers = Layers(points=True, labels=True, axis=True, roi=True)
        self.canvas.canvas_clicked.connect(self._on_click)
        self.canvas.point_dragged.connect(self._on_drag)
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.title = QLabel()
        f = QFont()
        f.setPointSizeF(13)
        f.setBold(True)
        self.title.setFont(f)

        self.fdi_box = QComboBox()
        self.fdi_box.addItem("牙位号未指定", None)
        for quadrant in range(1, 9):
            for number in range(1, 9 if quadrant <= 4 else 6):
                fdi = quadrant * 10 + number
                self.fdi_box.addItem(f"FDI {fdi}", fdi)
        self.fdi_box.setToolTip("复核并修改本牙的 FDI 牙位号")
        self.fdi_box.activated.connect(self._change_fdi)

        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet(f"color:{T.AI}; font-size:12pt; font-weight:600;")

        self.dir_hint = QLabel()
        self.dir_hint.setWordWrap(True)
        self.dir_hint.setMinimumHeight(34)
        self.dir_hint.setStyleSheet(f"color:{T.NIBI}; font-size:9pt; line-height:145%;")

        # 步骤清单
        self.step_labels: dict[tuple[str, str], QLabel] = {}
        self.site_heads = {}
        self.side_boxes = {}
        steps_box = QFrame()
        steps_box.setFrameShape(QFrame.Shape.StyledPanel)
        grid = QGridLayout(steps_box)
        grid.setContentsMargins(10, 8, 10, 8)
        grid.setVerticalSpacing(3)
        row = 0
        for sf in SURFACES:
            head = QLabel(f"— {SURFACE_LABEL[sf]}面 —")
            self.site_heads[sf] = head
            head.setStyleSheet(f"color:{T.NIBI}; font-weight:700;")
            grid.addWidget(head, row, 0, 1, 2)
            row += 1
            side_box = QComboBox()
            side_box.setToolTip("模型只识别图像左右。请根据实际牙位确认近中或远中")
            side_box.activated.connect(lambda i, s=sf: self._confirm_side(s, i))
            self.side_boxes[sf] = side_box
            grid.addWidget(side_box, row, 0, 1, 2)
            row += 1
            for r in ROLES:
                lbl = QLabel()
                lbl.setTextFormat(Qt.TextFormat.RichText)
                self.step_labels[(sf, r)] = lbl
                grid.addWidget(lbl, row, 0, 1, 2)
                row += 1
            cb = QCheckBox(f"跳过{SURFACE_LABEL[sf]}面（看不清 / 被遮挡）")
            cb.setStyleSheet(f"color:{T.YAMABUKI};")
            cb.toggled.connect(lambda on, s=sf: self._toggle_skip(s, on))
            setattr(self, f"_skip_{sf}", cb)
            grid.addWidget(cb, row, 0, 1, 2)
            row += 1

        self.metrics = QLabel()
        self.metrics.setTextFormat(Qt.TextFormat.RichText)
        self.metrics.setStyleSheet(
            f"background:{T.SHIRONERI}; border:1px solid {T.BORDER_SOFT};"
            f"border-radius:8px; padding:10px;"
        )
        self.metrics.setWordWrap(True)

        btn_undo = QPushButton("撤销上一点  (Backspace)")
        btn_undo.clicked.connect(self.undo)
        btn_clear = QPushButton("清空本牙")
        btn_clear.clicked.connect(self._clear_tooth)
        btn_fit = QPushButton("重新框住本牙  (F)")
        btn_fit.clicked.connect(self._fit_tooth)
        self.btn_hand = QPushButton("抓手平移  (H)")
        self.btn_hand.setCheckable(True)
        self.btn_hand.setToolTip("选中后在空白处左键拖动图像，已有标点仍可拖动；取消选中后点击空白落点")
        self.btn_hand.toggled.connect(self.canvas.set_hand_tool)
        self.btn_review = QPushButton("确认本牙候选坐标")
        self.btn_review.setToolTip("确认目前显示的候选位置；侧别仍需在上方另行确认")
        self.btn_review.clicked.connect(self._review_points)

        side = QVBoxLayout()
        side.addWidget(self.title)
        side.addWidget(self.fdi_box)
        side.addWidget(self.hint)
        side.addWidget(self.dir_hint)
        side.addSpacing(6)
        side.addWidget(steps_box)
        side.addSpacing(6)
        side.addWidget(self.metrics)
        side.addStretch(1)
        side.addWidget(btn_fit)
        side.addWidget(self.btn_hand)
        side.addWidget(self.btn_review)
        side.addWidget(btn_undo)
        side.addWidget(btn_clear)

        side_w = QWidget()
        side_w.setLayout(side)
        side_w.setFixedWidth(300)

        self.btn_prev = QPushButton("◂ 上一颗")
        self.btn_prev.clicked.connect(self.prev_tooth)
        self.btn_next = QPushButton("下一颗 ▸  (空格)")
        self.btn_next.clicked.connect(self.next_tooth)
        self.btn_done = QPushButton("完成标定")
        self.btn_done.setDefault(True)
        self.btn_done.clicked.connect(self.accept)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)

        bottom = QHBoxLayout()
        bottom.addWidget(btn_cancel)
        bottom.addStretch(1)
        bottom.addWidget(self.btn_prev)
        bottom.addWidget(self.btn_next)
        bottom.addWidget(self.btn_done)

        top = QHBoxLayout()
        top.addWidget(self.canvas, 1)
        top.addWidget(side_w)

        root = QVBoxLayout(self)
        root.addLayout(top, 1)
        root.addLayout(bottom)

    def _install_shortcuts(self) -> None:
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, activated=self._advance)
        QShortcut(QKeySequence(Qt.Key.Key_Backspace), self, activated=self.undo)
        QShortcut(QKeySequence("F"), self, activated=self._fit_tooth)
        QShortcut(QKeySequence("H"), self, activated=self.btn_hand.toggle)
        QShortcut(QKeySequence("S"), self, activated=self._skip_current_side)
        QShortcut(QKeySequence(Qt.Key.Key_PageDown), self, activated=self.next_tooth)
        QShortcut(QKeySequence(Qt.Key.Key_PageUp), self, activated=self.prev_tooth)

    # ── 当前状态 ──────────────────────────────────────────────────
    @property
    def tooth(self) -> Tooth:
        return self._teeth[self._ti]

    @property
    def step(self) -> tuple[str, str]:
        return STEPS[self._si]

    def _site(self, surface: str) -> Site:
        return self.tooth.site(surface)

    def _change_fdi(self, index: int) -> None:
        self.tooth.fdi = self.fdi_box.itemData(index)
        self._refresh_overlay()
        self._refresh()

    def _confirm_side(self, surface: str, index: int) -> None:
        target = self.side_boxes[surface].itemData(index)
        if target not in SURFACES:
            return
        site = self._site(surface)
        if target != surface:
            other = self._site(target)
            other.surface, site.surface = surface, target
            self.tooth.sites.sort(key=lambda s: SURFACES.index(s.surface))
            # Old undo slots would refer to a different group after the swap.
            self._undo.clear()
        site.side_confirmed = True
        self._refresh_overlay()
        self._refresh()

    def _review_points(self) -> None:
        for site in self.tooth.sites:
            for role, meta in getattr(site, "point_meta", {}).items():
                if site.get(role) is not None and meta.get("origin") == "model":
                    meta["review_status"] = "reviewed"
        self._refresh_overlay()
        self._refresh()

    # ── 导航 ─────────────────────────────────────────────────────
    def _goto_tooth(self, i: int) -> None:
        self._ti = max(0, min(i, len(self._teeth) - 1))
        self._si = self._first_unfilled_step()
        for sf in SURFACES:
            cb = getattr(self, f"_skip_{sf}")
            cb.blockSignals(True)
            cb.setChecked(self._site(sf).skipped)
            cb.blockSignals(False)
        self.canvas.set_case(self._gray, self._ann, self._formula, self._fcfg)
        self._fit_tooth()
        self._refresh()

    def _first_unfilled_step(self) -> int:
        for i, (sf, r) in enumerate(STEPS):
            site = self._site(sf)
            if site.skipped:
                continue
            if site.get(r) is None:
                return i
        return len(STEPS) - 1

    def _tooth_complete(self) -> bool:
        return all(self._site(sf).skipped or all(self._site(sf).get(role) is not None for role in ROLES)
                   for sf in SURFACES)

    def _advance(self) -> None:
        """空格：跳到下一个未填的点；本牙填满就跳下一颗。"""
        # Search the whole tooth before advancing, including any earlier hole.
        order = list(range(self._si + 1, len(STEPS))) + list(range(self._si + 1))
        for i in order:
            sf, r = STEPS[i]
            if self._site(sf).skipped:
                continue
            if self._site(sf).get(r) is None:
                self._si = i
                self._refresh()
                return
        if self._ti < len(self._teeth) - 1:
            self.next_tooth()
        else:
            self._si = self._first_unfilled_step()
            self._refresh()

    def next_tooth(self) -> None:
        if self._ti < len(self._teeth) - 1:
            self._goto_tooth(self._ti + 1)

    def prev_tooth(self) -> None:
        if self._ti > 0:
            self._goto_tooth(self._ti - 1)

    def _fit_tooth(self) -> None:
        """把视野缩放到这颗牙的框。

        画布里放的是**完整全景片**，只是视野落在框上 ——
        所以根尖永远不会被裁掉，需要时随手滚轮缩小就能看到牙的全貌。
        """
        roi = self.tooth.roi
        if not roi:
            self.canvas.fit()
            return
        x, y, w, h = roi
        pad = max(w, h) * 0.12
        # 走 ZoomCanvas.fit：widget 还没布局完时它会记账，showEvent 里自动补
        self.canvas.fit(QRectF(x - pad, y - pad, w + 2 * pad, h + 2 * pad))

    # ── 落点 / 拖点 ───────────────────────────────────────────────
    def _on_click(self, pos: QPointF) -> None:
        if self._tooth_complete():
            self._refresh()
            return
        sf, role = self.step
        site = self._site(sf)
        if site.skipped:
            self._advance()
            return
        self._undo.append((self.tooth, sf, role, site.get(role)))
        site.set(role, Pt(pos.x(), pos.y()))
        self._advance_after_place()

    def _advance_after_place(self) -> None:
        self._refresh_overlay()
        self._advance()

    def _on_drag(self, tooth: Tooth, site: Site, role: str, pos: QPointF) -> None:
        p = site.get(role)
        if p is None:
            return
        site.set(role, Pt(pos.x(), pos.y()))
        self._refresh_texts()          # 拖动中只更新数字，避免重建图元导致抖动

    def undo(self) -> None:
        if not self._undo:
            return
        tooth, sf, role, old = self._undo.pop()
        tooth.site(sf).set(role, old)
        if tooth in self._teeth:
            self._goto_tooth(self._teeth.index(tooth))
        self._si = STEPS.index((sf, role))
        self._refresh_overlay()
        self._refresh()

    def _goto_index_of(self, tooth: Tooth) -> None:
        if tooth in self._teeth:
            self._ti = self._teeth.index(tooth)

    def _clear_tooth(self) -> None:
        for sf in SURFACES:
            site = self._site(sf)
            for r in ROLES:
                if site.get(r) is not None:
                    self._undo.append((self.tooth, sf, r, site.get(r)))
                site.set(r, None)
        self._si = 0
        self._refresh_overlay()
        self._refresh()

    def _toggle_skip(self, surface: str, on: bool) -> None:
        self._site(surface).skipped = on
        if on:
            self._advance()
        else:
            self._si = self._first_unfilled_step()
        self._refresh_overlay()
        self._refresh()

    def _skip_current_side(self) -> None:
        sf = self.step[0]
        cb = getattr(self, f"_skip_{sf}")
        cb.setChecked(not cb.isChecked())

    # ── 刷新 ─────────────────────────────────────────────────────
    def _refresh_overlay(self) -> None:
        self.canvas.refresh_overlay()

    def _refresh(self) -> None:
        t = self.tooth
        self.title.setText(f"标定 {self._ti + 1}/{len(self._teeth)} · 牙位 {t.name}")
        self.fdi_box.setCurrentIndex(max(0, self.fdi_box.findData(t.fdi)))
        pending = False
        for sf in SURFACES:
            site = self._site(sf)
            label = getattr(site, "display_label", SURFACE_LABEL[sf])
            self.site_heads[sf].setText(f"— {label} —")
            skip = getattr(self, f"_skip_{sf}")
            skip.setText("跳过此组（看不清 / 被遮挡）")
            skip.setToolTip(label)
            skip.blockSignals(True)
            skip.setChecked(site.skipped)
            skip.blockSignals(False)
            box = self.side_boxes[sf]
            box.blockSignals(True)
            box.clear()
            box.addItem("请确认邻面…", None)
            for target in SURFACES:
                text = f"确认为{SURFACE_LABEL[target]}"
                if target != sf:
                    text += "（互换两组）"
                box.addItem(text, target)
            confirmed = getattr(site, "side_confirmed", True)
            box.setCurrentIndex(box.findData(sf) if confirmed else 0)
            box.setVisible(getattr(site, "image_side", None) is not None)
            box.blockSignals(False)
            pending |= any(meta.get("origin") == "model" and meta.get("review_status") != "reviewed"
                           for meta in getattr(site, "point_meta", {}).values())
        self.btn_review.setEnabled(pending)

        sf, role = self.step
        n = point_label(t.index, sf, role)
        side_label = getattr(self._site(sf), "display_label", SURFACE_LABEL[sf])
        if self._tooth_complete():
            self.hint.setText("本牙已标完或明确跳过。点击「完成标定」保存，再回主窗导出。"
                              if self._ti == len(self._teeth) - 1 else
                              "本牙已标完或明确跳过，可进入下一颗；拖动现有标点可继续复核。")
        else:
            self.hint.setText(f"当前步骤：{n}　{side_label} · {ROLE_LABEL[role]}")

        upper = bool(t.fdi and t.fdi // 10 in (1, 2, 5, 6))
        self.dir_hint.setText(
            "上颌牙：牙冠在下、根尖朝上，四个点由下往上依次标"
            if upper else
            "下颌牙：牙冠在上、根尖朝下，四个点由上往下依次标"
        )

        for (s, r), lbl in self.step_labels.items():
            site = self._site(s)
            label = point_label(t.index, s, r)
            filled = site.get(r) is not None
            meta = getattr(site, "point_meta", {}).get(r, {})
            candidate = meta.get("origin") == "model" and meta.get("review_status") != "reviewed"
            if site.skipped:
                mark, color = "—", T.USUZUMI
            elif (s, r) == self.step and not self._tooth_complete():
                mark, color = "●", T.AI
            elif filled:
                mark, color = ("候", T.YAMABUKI) if candidate else ("✓", T.MATSUBA)
            else:
                mark, color = "○", T.USUZUMI
            weight = "700" if (s, r) == self.step else "400"
            lbl.setText(
                f'<span style="color:{color};font-weight:{weight}">'
                f"{mark} {label} &nbsp; {ROLE_SHORT[r]}</span>"
            )

        self.btn_prev.setEnabled(self._ti > 0)
        self.btn_next.setEnabled(self._ti < len(self._teeth) - 1)
        self._refresh_texts()

    def _refresh_texts(self) -> None:
        t = self.tooth
        rows = []
        for sf in SURFACES:
            site = self._site(sf)
            name = getattr(site, "display_label", SURFACE_LABEL[sf])
            if site.skipped:
                rows.append(f'<tr><td>{name}</td><td colspan="3" '
                            f'style="color:{T.USUZUMI}">已跳过</td></tr>')
                continue
            m = site.metrics(self._formula, self._fcfg)
            if m is None:
                rows.append(f'<tr><td>{name}</td><td colspan="3" '
                            f'style="color:{T.NIBI}">待标定 '
                            f"({sum(site.get(r) is not None for r in self._formula.needs)}/{len(self._formula.needs)})</td></tr>")
                continue
            color = T.MATSUBA
            note = ""
            if "too_short" in m.warnings:
                color, note = T.SHU, " ⚠根长过短"
            elif "ratio_gt_1" in m.warnings:
                color, note = T.YAMABUKI, " ⚠比值&gt;1，请复核"
            elif m.no_loss:
                color, note = T.AI, " 未见吸收"
            rows.append(
                f"<tr><td>{name}</td>"
                f'<td style="color:{color};font-weight:700">{m.ratio:.3f}</td>'
                f'<td style="color:{T.USUZUMI}">根长{m.root_length:.0f}px</td>'
                f'<td style="color:{T.USUZUMI}">吸收{m.bone_loss:.0f}px{note}</td></tr>'
            )

        _, best = t.worst(self._formula, self._fcfg)
        best_txt = (
            f'<div style="margin-top:6px">本牙取大：'
            f'<b style="color:{T.SHU}">{best.ratio:.3f}</b></div>'
            if best else
            f'<div style="margin-top:6px;color:{T.NIBI}">本牙取大：—</div>'
        )
        self.metrics.setText(
            '<table width="100%" cellspacing="2">' + "".join(rows) + "</table>" + best_txt
        )
