"""右栏：病例信息 + 测量位点 + 结果。

⚠️ 只给事实，不下分期分级结论 —— Stage / Grade 需要缺牙数、探诊深度、
   根分叉、病史、吸烟糖尿病等临床资料，全景片给不了。
   这里输出：骨吸收比例、骨吸收年龄比，以及比例落在 2018 分类的哪个影像学区间。

界面上显示的所有数字都是**当场算出来的**，不是从文件里读的 ——
换公式或改阈值后，这里立刻跟着变。
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.export import COMPARE_IDS, COMPARE_NAMES, both_ratios
from ..core.formula import FORMULAS
from ..core.grading import GradingConfig, interval_of, interval_text
from ..core.models import POINTS_PER_SITE, SURFACE_LABEL, CaseAnnotation
from . import theme as T

INTERVAL_COLORS = {"I": T.MATSUBA, "II": T.YAMABUKI, "III": T.SHU}


class IntervalBar(QWidget):
    """2018 影像学骨吸收区间尺：三段刻度 + 当前值指针。

    只标出数值落在哪一段，**不等于 Stage 分期**。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(46)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._ratio: float | None = None
        self._cfg = GradingConfig()

    def set_value(self, ratio: float | None, cfg: GradingConfig) -> None:
        self._ratio, self._cfg = ratio, cfg
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, top, h = self.width(), 16.0, 9.0
        a, b = self._cfg.interval_i_max, self._cfg.interval_ii_max
        # 尺子右端要跟着数值走，否则重度吸收（>50%）的指针会被压在边框上看不出来
        vmax = max(0.5, b * 1.55, (self._ratio or 0) * 1.18)

        segs = [(0.0, a, "I"), (a, b, "II"), (b, vmax, "III")]
        for lo, hi, key in segs:
            x0, x1 = lo / vmax * w, hi / vmax * w
            active = self._ratio is not None and interval_of(self._ratio, self._cfg) == key
            col = QColor(INTERVAL_COLORS[key])
            if not active:
                col.setAlphaF(0.22)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col)
            p.drawRoundedRect(QRectF(x0 + 1, top, max(2.0, x1 - x0 - 2), h), 4, 4)

        f = QFont()
        f.setPointSizeF(7.5)
        p.setFont(f)
        p.setPen(QPen(QColor(T.NIBI)))
        for lo, hi, _k in segs[:2]:
            x = hi / vmax * w
            p.drawText(QRectF(x - 22, top + h + 1, 44, 13),
                       Qt.AlignmentFlag.AlignCenter, f"{hi * 100:g}%")

        if self._ratio is None:
            return
        x = min(max(self._ratio, 0.0), vmax) / vmax * w
        key = interval_of(self._ratio, self._cfg)
        col = QColor(INTERVAL_COLORS.get(key, T.SUMI))
        p.setPen(QPen(col, 2))
        p.drawLine(int(x), int(top - 5), int(x), int(top + h + 3))
        f.setBold(True)
        f.setPointSizeF(8.5)
        p.setFont(f)
        p.setPen(QPen(col))
        rect = QRectF(max(0.0, min(x - 32, w - 64)), 0, 64, 14)
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{self._ratio * 100:.1f}%")


class InspectorPanel(QWidget):
    patient_changed = Signal()
    formula_changed = Signal(str)
    tooth_remove_requested = Signal(int)        # tooth.index
    clear_all_requested = Signal()              # 一键清空本片所有标记

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ann: CaseAnnotation | None = None
        self._cfg = GradingConfig()
        self._loading = False
        self._periapical = False
        self._patient_worst: tuple[str, float] | None = None   # (片名, 比例)
        self.setMinimumWidth(300)

        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(6)

        lay.addWidget(self._section("病例信息"))
        lay.addWidget(self._build_patient())
        lay.addWidget(self._section("测量位点"))
        lay.addWidget(self._build_table())
        lay.addWidget(self.btn_remove)
        lay.addWidget(self.btn_clear)
        lay.addWidget(self._section("结果"))
        lay.addWidget(self._build_result())
        lay.addWidget(self._section("计算公式"))
        lay.addWidget(self._build_formula())
        lay.addSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(body)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ── 构件 ─────────────────────────────────────────────────────
    @staticmethod
    def _section(text: str) -> QLabel:
        lbl = QLabel(text)
        f = QFont()
        f.setBold(True)
        f.setPointSizeF(9.5)
        lbl.setFont(f)
        lbl.setStyleSheet(
            f"color:{T.AI}; margin-top:8px; padding-bottom:2px;"
            f"border-bottom:1px solid {T.BORDER_SOFT};"
        )
        return lbl

    def _build_patient(self) -> QWidget:
        self.case_id = QLineEdit()
        self.case_id.setPlaceholderText("病例号 / 患者编号")
        self.case_id.setToolTip("可直接编辑。导出时用这个值作为病例标识。")
        self.case_id.editingFinished.connect(self._on_edit)

        self.age = QDoubleSpinBox()
        self.age.setRange(0, 129)
        self.age.setDecimals(0)
        self.age.setSpecialValueText("未填")
        self.age.setSuffix(" 岁")
        self.age.valueChanged.connect(self._on_edit)

        self.sex = QComboBox()
        self.sex.addItems(["", "男", "女"])
        self.sex.currentTextChanged.connect(self._on_edit)

        self.note = QLineEdit()
        self.note.setPlaceholderText("备注…")
        self.note.editingFinished.connect(self._on_edit)

        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(0, 4, 0, 0)
        form.setSpacing(6)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.addRow("病例号", self.case_id)
        form.addRow("年龄", self.age)
        form.addRow("性别", self.sex)
        form.addRow("备注", self.note)
        return w

    def _build_table(self) -> QWidget:
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["牙位", "邻面", "点", "比值"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        hh = self.table.horizontalHeader()
        # 四列**等分**可用宽度。右栏只有 ~380px：
        #   · ResizeToContents 会在栏窄时把右边的列挤出可视区
        #   · 只让某一列 Stretch，则那一列会吃掉全部余量、把别的列挤掉
        # 等分是唯一在任意栏宽下都不丢列的方案。
        # 所以表只留 4 列，根长/吸收挪进行提示（tooltip），完整明细看导出的 CSV。
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        hh.setMinimumSectionSize(36)

        self.btn_remove = QPushButton("删除选中的牙")
        self.btn_remove.clicked.connect(self._on_remove)

        self.btn_clear = QPushButton("一键清空所有标记")
        self.btn_clear.setToolTip("清空本片全部牙位与标定点（会先二次确认）")
        self.btn_clear.setStyleSheet(
            f"QPushButton{{color:{T.SHU};border-color:{T.BORDER};}}"
            f"QPushButton:hover{{background:{T.SHU_WASH};border-color:{T.SHU};}}"
        )
        self.btn_clear.clicked.connect(self.clear_all_requested.emit)
        return self.table

    def _build_result(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(4)

        self.result = QLabel()
        self.result.setTextFormat(Qt.TextFormat.RichText)
        self.result.setWordWrap(True)
        self.result.setStyleSheet(
            f"background:{T.SHIRONERI}; border:1px solid {T.BORDER_SOFT};"
            f"border-radius:8px; padding:10px;"
        )
        self.bar = IntervalBar()
        self.bar_caption = QLabel()
        self.bar_caption.setWordWrap(True)
        self.bar_caption.setTextFormat(Qt.TextFormat.RichText)
        self.bar_caption.setMinimumHeight(38)
        self.bar_caption.setSizePolicy(QSizePolicy.Policy.Preferred,
                                       QSizePolicy.Policy.Minimum)
        self.bar_caption.setStyleSheet(
            f"color:{T.NIBI}; font-size:8pt; line-height:150%;"
        )

        v.addWidget(self.result)
        v.addWidget(self.bar)
        v.addWidget(self.bar_caption)
        return w

    def _build_formula(self) -> QWidget:
        self.formula_box = QComboBox()
        for f in FORMULAS.values():
            self.formula_box.addItem(f.label, f.id)
        # 公式名很长（"④ 投影法·CEJ下2mm 起点：③式投影到牙长轴后再相除"）。
        # 不限制的话它的 sizeHint 会把整个右栏撑宽，进而把位点表的比值列挤出可视区。
        # 收窄控件本身、放宽弹出列表，两边都好看。
        self.formula_box.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.formula_box.setMinimumContentsLength(10)
        self.formula_box.view().setMinimumWidth(460)
        self.formula_box.setToolTip(
            "两个公式用完全相同的 3 个点，只是分子的量法不同：\n"
            "  ① 直线法：分子 = CEJ 到牙槽嵴顶的直线距离\n"
            "  ② 投影法：分子 = 上述向量在 CEJ→根尖长轴上的投影\n"
            "分母都是 CEJ 到根尖的距离。切换后一键重算，不用重标。"
        )
        self.formula_box.currentIndexChanged.connect(self._on_formula)

        self.formula_hint = QLabel()
        self.formula_hint.setWordWrap(True)
        self.formula_hint.setTextFormat(Qt.TextFormat.RichText)
        self.formula_hint.setMinimumHeight(56)
        self.formula_hint.setSizePolicy(QSizePolicy.Policy.Preferred,
                                        QSizePolicy.Policy.Minimum)
        self.formula_hint.setStyleSheet(
            f"color:{T.NIBI}; font-size:8pt; line-height:150%;"
        )

        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(4)
        v.addWidget(self.formula_box)
        v.addWidget(self.formula_hint)
        return w

    # ── 载入 / 刷新 ───────────────────────────────────────────────
    def set_periapical(self, on: bool) -> None:
        self._periapical = on
        self.refresh()

    def set_patient_worst(self, info: tuple[str, float] | None) -> None:
        """根尖片模式下，同一病人跨全部片子的最重位点 (片名, 比例)。"""
        self._patient_worst = info
        self.refresh()

    def set_case(self, ann: CaseAnnotation | None, cfg: GradingConfig) -> None:
        self._ann = ann
        self._cfg = cfg
        self._loading = True
        if ann is None:
            for w in (self.case_id, self.note):
                w.clear()
            self.age.setValue(0)
            self.sex.setCurrentIndex(0)
        else:
            self.case_id.setText(ann.patient.id)
            self.age.setValue(ann.patient.age or 0)
            self.sex.setCurrentText(ann.patient.sex or "")
            self.note.setText(ann.patient.note)
            i = self.formula_box.findData(ann.formula_id)
            if i >= 0:
                self.formula_box.setCurrentIndex(i)
        self._loading = False
        self.setEnabled(ann is not None)
        self.refresh()

    def refresh(self) -> None:
        ann, cfg = self._ann, self._cfg
        f = FORMULAS.get(self.formula_box.currentData())
        self.formula_hint.setText(f.description.replace("\n", "<br>") if f else "")

        if ann is None:
            self.table.setRowCount(0)
            self._autosize_table()
            self.result.setText("—")
            self.bar.set_value(None, cfg)
            self.bar_caption.clear()
            return

        rows = [r for r in ann.all_metrics(cfg)
                if r[1].filled_count > 0 or r[1].skipped]
        res = ann.compute(cfg)
        self._fill_table(rows, res)
        self.result.setText(self._result_html(ann, res))
        self.bar.set_value(res.worst_ratio, cfg)
        self.bar_caption.setText(
            "2018 分类的影像学骨吸收范围区间，仅说明数值落点。<br>"
            "<b>这不是 Stage 分期结论</b> —— 分期分级需结合缺牙数、探诊深度、"
            "根分叉、病史等临床资料，由医生判断。"
            if res.worst_ratio is not None else ""
        )

    def _autosize_table(self) -> None:
        """按行数定高，保证每一行位点都看得见（不做内部滚动）。"""
        h = self.table.horizontalHeader().height() + 2
        for i in range(self.table.rowCount()):
            h += self.table.rowHeight(i)
        self.table.setFixedHeight(max(h, 64))

    def _fill_table(self, rows, res) -> None:
        self.table.setRowCount(len(rows))
        for i, (tooth, site, m) in enumerate(rows):
            vals = [
                tooth.name,
                SURFACE_LABEL.get(site.surface, site.surface),
                "—" if site.skipped else f"{site.filled_count}/{POINTS_PER_SITE}",
                "跳过" if site.skipped else ("—" if m is None else f"{m.ratio:.3f}"),
            ]
            tip = (f"根长 {m.root_length:.1f}px　骨吸收 {m.bone_loss:.1f}px"
                   if m else "该公式所需的点还没标齐")
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setToolTip(tip)
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
                )
                if c == 0:
                    item.setForeground(QColor(tooth.color).darker(135))
                    item.setData(Qt.ItemDataRole.UserRole, tooth.index)
                if c == 2 and not site.skipped and site.filled_count < POINTS_PER_SITE:
                    item.setForeground(QColor(T.YAMABUKI))   # 点没标满，③④算不出
                if site is res.worst_site:
                    fnt = item.font()
                    fnt.setBold(True)
                    item.setFont(fnt)
                    if c == 3:
                        item.setForeground(QColor(T.SHU))
                        item.setText("★ " + item.text())
                elif m is not None and c == 3:
                    if "ratio_gt_1" in m.warnings:
                        item.setForeground(QColor(T.YAMABUKI))
                    elif "too_short" in m.warnings:
                        item.setForeground(QColor(T.SHU))
                self.table.setItem(i, c, item)
        self._autosize_table()

    def _result_html(self, ann: CaseAnnotation, res) -> str:
        def row(k, v, color=T.SUMI, big=False):
            size = "15pt" if big else "10pt"
            return (
                f'<tr><td style="color:{T.NIBI};padding-right:10px">{k}</td>'
                f'<td style="color:{color};font-size:{size};font-weight:700">{v}</td></tr>'
            )

        if res.worst_metrics is None:
            return f'<span style="color:{T.NIBI}">尚未标定任何完整位点</span>'

        where = f"{res.worst_tooth.name} {SURFACE_LABEL.get(res.worst_site.surface, '')}"
        icol = INTERVAL_COLORS.get(res.interval, T.SUMI)
        html = ['<table cellspacing="3">']
        html.append(row("本片最重位点" if self._periapical else "最重位点", where))
        html.append(row("骨吸收比例",
                        f"{res.worst_ratio:.3f}"
                        f'<span style="font-size:10pt;color:{T.NIBI}">'
                        f"　({res.worst_ratio * 100:.1f}%)</span>", T.AI, big=True))
        if res.bone_loss_age_ratio is None:
            html.append(row("骨吸收年龄比", "需填年龄", T.SHU))
        else:
            html.append(row("骨吸收年龄比", f"{res.bone_loss_age_ratio:.4f}"))
        html.append(row("所属区间", interval_text(res.interval, self._cfg), icol))
        html.append("</table>")

        m = res.worst_metrics
        html.append(
            f'<div style="color:{T.USUZUMI};margin-top:7px;font-size:8pt">'
            f"根长 {m.root_length:.1f}px · 骨吸收 {m.bone_loss:.1f}px · "
            f"本片已标 {ann.annotated_tooth_count} 颗牙</div>"
        )
        if self._periapical and self._patient_worst is not None:
            film, ratio = self._patient_worst
            same = abs(ratio - (res.worst_ratio or 0)) < 1e-9
            html.append(
                f'<div style="margin-top:5px;font-size:8pt;color:{T.AI}">'
                f"该病人全口最重：<b>{ratio:.3f}（{ratio * 100:.1f}%）</b>"
                + ("　← 就在本片" if same else f"　在《{film}》") + "</div>"
            )

        # 四个公式同时列出，当前生效的用 ● 标出
        vals = both_ratios(res.worst_site, self._cfg)
        if any(v is not None for v in vals.values()):
            active = ann.formula_id
            cells = []
            for fid in COMPARE_IDS:
                v = vals[fid]
                cur = fid == active
                color = T.AI if cur else (T.NIBI if v is not None else T.USUZUMI)
                weight = "700" if cur else "400"
                shown = f"{v:.3f}" if v is not None else "缺 P2"
                cells.append(
                    f'<td style="color:{color};font-weight:{weight};padding-right:9px">'
                    f'{"●" if cur else "○"} {COMPARE_NAMES[fid]} {shown}</td>'
                )
            html.append(
                '<table style="margin-top:5px;font-size:8pt" cellspacing="0"><tr>'
                + "".join(cells[:2]) + "</tr><tr>" + "".join(cells[2:]) + "</tr></table>"
            )
            tilt = vals["direct_v1"], vals["projection_v1"]
            orig = vals["direct_v1"], vals["direct_cej2_v1"]
            notes = []
            if all(x is not None for x in tilt):
                notes.append(f"倾斜高估 {tilt[0] - tilt[1]:+.3f}")
            if all(x is not None for x in orig):
                notes.append(f"起点差异 {orig[0] - orig[1]:+.3f}")
            if notes:
                html.append(f'<div style="color:{T.USUZUMI};font-size:8pt">'
                            + "　·　".join(notes) + "</div>")
        if m.no_loss:
            html.append(f'<div style="color:{T.AI};font-size:8pt;margin-top:3px">'
                        "该位点 AC 位于 CEJ 冠方，未见骨吸收（比值为负，如实保留）</div>")
        return "".join(html)

    # ── 事件 ─────────────────────────────────────────────────────
    def _on_edit(self, *_):
        if self._loading or self._ann is None:
            return
        p = self._ann.patient
        p.id = self.case_id.text().strip()
        p.age = self.age.value() or None
        p.sex = self.sex.currentText()
        p.note = self.note.text()
        self.refresh()
        self.patient_changed.emit()

    def _on_formula(self, *_):
        if self._loading or self._ann is None:
            return
        fid = self.formula_box.currentData()
        if fid and fid != self._ann.formula_id:
            self._ann.formula_id = fid
            self.formula_changed.emit(fid)
        self.refresh()

    def _on_remove(self):
        items = self.table.selectedItems()
        if not items:
            return
        idx = self.table.item(items[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        if idx is not None:
            self.tooth_remove_requested.emit(int(idx))
