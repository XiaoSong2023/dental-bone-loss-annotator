"""设置 —— 区间阈值、数据校验、项目行为。

⚠️ 这里没有 Stage / Grade 的阈值 —— 软件不下分期分级结论。
   只有 2018 分类的**影像学骨吸收范围**分界（<15% / 15%–33% / >33%），
   用来说明数值落在哪一段，最终判断由医生结合临床完成。
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QVBoxLayout,
)

from ..core.grading import GradingConfig
from ..core.project import ProjectSettings
from . import theme as T


def _spin(v: float, lo: float, hi: float, step: float = 0.01, dec: int = 3) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setSingleStep(step)
    s.setDecimals(dec)
    s.setValue(v)
    return s


def _note(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(f"color:{T.NIBI}; font-size:8pt;")
    return lbl


class SettingsDialog(QDialog):
    def __init__(self, grading: GradingConfig, settings: ProjectSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.resize(470, 460)
        self._g = grading
        self._s = settings

        # ── 区间 ──
        self.i_max = _spin(grading.interval_i_max, 0.0, 1.0)
        self.ii_max = _spin(grading.interval_ii_max, 0.0, 1.0)
        g1 = QGroupBox("骨吸收比例区间（2018 影像学骨吸收范围）")
        f1 = QFormLayout(g1)
        f1.addRow("第一段上限 <", self.i_max)
        f1.addRow("第二段上限 ≤", self.ii_max)
        f1.addRow(_note(
            "默认 0.15 / 0.33，即 &lt;15% · 15%–33% · &gt;33%。<br>"
            "<b>这只是数值落点，不是 Stage 分期结论</b> —— 分期分级需结合缺牙数、"
            "探诊深度、根分叉、病史等临床资料，由医生判断。"
        ))

        # ── 校验 ──
        self.min_root = _spin(grading.min_root_px, 1.0, 500.0, 1.0, 1)
        self.warn_above = _spin(grading.ratio_warn_above, 0.1, 5.0)
        g2 = QGroupBox("数据校验")
        f2 = QFormLayout(g2)
        f2.addRow("根长下限（像素）", self.min_root)
        f2.addRow("比值告警阈值 >", self.warn_above)
        f2.addRow(_note(
            "根长过短判为误标（红色）；比值超过阈值提示复核（黄色），但不阻断。"
        ))

        # ── 项目 ──
        self.physical = QCheckBox("完成时把图片物理移动到 images/done/")
        self.physical.setChecked(settings.physical_archive)
        self.physical.setToolTip(
            "默认关闭。逻辑归档（列表 Tab 分组）已经能满足「已完成/未完成一目了然」，\n"
            "而物理移动研究原始数据后想回滚会很麻烦。"
        )
        self.copy_import = QCheckBox("导入时把原图复制进项目（推荐）")
        self.copy_import.setChecked(settings.copy_on_import)
        self.copy_import.setToolTip("关闭后只记录原图的绝对路径，原图移动或改名会失联。")
        g3 = QGroupBox("项目")
        f3 = QVBoxLayout(g3)
        for w in (self.physical, self.copy_import):
            f3.addWidget(w)
        box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        for w in (g1, g2, g3):
            lay.addWidget(w)
        lay.addStretch(1)
        lay.addWidget(box)

    def apply(self) -> None:
        self._g.interval_i_max = self.i_max.value()
        self._g.interval_ii_max = self.ii_max.value()
        self._g.min_root_px = self.min_root.value()
        self._g.ratio_warn_above = self.warn_above.value()
        self._s.physical_archive = self.physical.isChecked()
        self._s.copy_on_import = self.copy_import.isChecked()
