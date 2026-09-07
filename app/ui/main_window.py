"""主窗口 —— 三栏布局与全部工作流。

左：病例列表 + 进度（可收起）　　中：全景片画布　　右：信息 / 位点 / 结果

布局要点：
  · 上下两条都是真正的 QToolBar。QToolBar 在空间不足时会自动折叠成 ">>" 溢出
    菜单，**不会把按钮文字裁掉** —— 这是第一版底部文字被切掉的根因。
  · 看片调节与图层开关收进弹出面板，底部只留主线操作，界面不再拥挤。
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from copy import deepcopy
from pathlib import Path

import numpy as np
from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSlider,
    QSplitter,
    QStatusBar,
    QToolBar,
    QToolButton,
    QWidget,
    QWidgetAction,
)

from ..core import export as exporter
from ..core import roster as roster_mod
from ..core.formula import FORMULAS, choices as formula_choices, get as get_formula
from ..core.models import CaseAnnotation, Pt, Tooth
from ..core.review_geometry import (constrain_pending_candidates, replacement_candidates,
                                   edit_box, undo_box, can_undo_box)
from ..core.project import (
    MODE_LABEL,
    MODE_PERIAPICAL,
    STATUS_DONE,
    STATUS_FLAGGED,
    STATUS_IN_PROGRESS,
    STATUS_PENDING,
    CaseEntry,
    Project,
)
from ..imaging.loader import ImageAdjust, apply_adjust, imwrite_unicode, load_gray
from ..imaging.segmenter import guess_fdi
from . import theme as T
from .ai_client import AiClient
from .case_panel import CasePanel
from .inspector_panel import InspectorPanel
from .panorama_view import MODE_PICK, MODE_VIEW, MODE_HAND, PanoramaView
from .settings_dialog import SettingsDialog
from .tooth_dialog import ToothDialog

ORG, APP = "PerioTools", "全景片牙槽骨吸收测量"
# APP 同时用作 QSettings 的键，**不要改** —— 改了用户的窗口位置/上次项目就丢了。
# 界面上显示的名字用 APP_TITLE（软件已同时支持全景片与根尖片，原名不再准确）。
APP_TITLE = "牙槽骨吸收测量"


class MainWindow(QMainWindow):
    def __init__(self, annotation_mode=None):
        super().__init__()
        # Legacy callers may still pass annotation_mode; all use the same UI.
        self._mode_title = APP_TITLE
        self.setWindowTitle(self._mode_title)
        self.resize(1560, 940)

        self.project: Project | None = None
        self.entry: CaseEntry | None = None
        self.ann: CaseAnnotation | None = None
        self._gray: np.ndarray | None = None
        self._adjust = ImageAdjust()
        self._t0: float | None = None
        self._dirty = False
        self._sidebar_width = 320
        self._ai_busy = False
        self._ai_context = None
        self._ai = AiClient(self)
        self._ai.progress.connect(self._ai_progress)
        self._ai.completed.connect(self._ai_completed)
        self._ai.failed.connect(self._ai_failed)
        self._ai.cancelled.connect(self._ai_cancelled)

        self._build_ui()
        self._build_menus()
        self._build_toolbars()
        self._build_shortcuts()
        self._restore_geometry()

        self._autosave = QTimer(self)
        self._autosave.setInterval(20_000)
        self._autosave.timeout.connect(lambda: self.save_current(silent=True))
        self._autosave.start()
        self._update_enabled()

    # ══ 界面骨架 ════════════════════════════════════════════════════
    def _build_ui(self) -> None:
        self.cases = CasePanel()
        self.cases.case_selected.connect(self.open_case)
        self.cases.rename_requested.connect(self.rename_case)
        self.cases.delete_requested.connect(self.delete_cases)
        self.cases.reveal_requested.connect(self.reveal_case)
        self.cases.regroup_requested.connect(self.regroup_cases)

        self.view = PanoramaView()
        self.view.box_drawn.connect(self._on_box_drawn)
        self.view.tooth_activated.connect(self.start_annotation)
        self.view.point_dragged.connect(self._on_point_dragged)
        self.view.moved.connect(self._on_mouse_moved)

        self.inspector = InspectorPanel()
        self.inspector.patient_changed.connect(self._on_patient_changed)
        self.inspector.formula_changed.connect(self.set_formula)
        self.inspector.tooth_remove_requested.connect(self._remove_tooth)
        self.inspector.clear_all_requested.connect(self.clear_all_marks)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.addWidget(self.cases)
        split.addWidget(self.view)
        split.addWidget(self.inspector)
        split.setStretchFactor(1, 1)
        split.setSizes([320, 880, 380])
        self.splitter = split
        self.setCentralWidget(split)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.hint_label = QLabel()
        self.hint_label.setStyleSheet(f"color:{T.NIBI};")
        self.pos_label = QLabel()
        self.pos_label.setStyleSheet(f"color:{T.USUZUMI};")
        self.status.addWidget(self.hint_label, 1)
        self.status.addPermanentWidget(self.pos_label)

    # ══ 菜单 ════════════════════════════════════════════════════════
    def _build_menus(self) -> None:
        m = self.menuBar()
        edit_menu = m.addMenu("编辑(&E)")
        self.act_undo_box = self._act(edit_menu, "撤销框选", self.undo_box_edit, "Ctrl+Z")
        self.act_snap = self._act(edit_menu, "候选点贴合牙齿轮廓", self.snap_candidates)

        fm = m.addMenu("项目(&P)")
        self._act(fm, "新建项目…", self.new_project, "Ctrl+N")
        self._act(fm, "打开项目…", self.open_project, "Ctrl+O")
        fm.addSeparator()
        self.act_import = self._act(fm, "批量导入全景片…", self.import_images, "Ctrl+I")
        self.act_roster = self._act(fm, "导入名册（年龄/性别）…", self.import_roster)
        fm.addSeparator()
        self.act_save = self._act(fm, "保存当前标注", lambda: self.save_current(), "Ctrl+S")
        fm.addSeparator()
        self._act(fm, "退出", self.close)

        em = m.addMenu("导出(&E)")
        self.act_csv = self._act(em, "导出 CSV（汇总 + 位点明细）", self.export_csv)
        self.act_xlsx = self._act(em, "导出 Excel", self.export_excel)
        self.act_json = self._act(em, "导出当前病例 JSON…", self.export_json)

        vm = m.addMenu("视图(&V)")
        self.act_sidebar = self._act(vm, "显示 / 隐藏病例列表", self.toggle_sidebar, "Ctrl+B")
        self.act_sidebar.setCheckable(True)
        self.act_sidebar.setChecked(True)
        self._act(vm, "适配窗口", self.view.fit, "Ctrl+0")

        tm = m.addMenu("工具(&T)")
        self.act_recalc = self._act(tm, "全部重算（换公式/改阈值后用）", self.recalculate_all)
        tm.addSeparator()
        self._act(tm, "设置…", self.open_settings)

        hm = m.addMenu("帮助(&H)")
        self._act(hm, "快捷键与用法", self.show_help, "F1")
        self._act(hm, "关于", self.show_about)

    def _act(self, parent, text, slot, shortcut: str | None = None) -> QAction:
        a = QAction(text, self)
        a.triggered.connect(slot)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        parent.addAction(a)
        return a

    # ══ 工具栏 ══════════════════════════════════════════════════════
    def _build_toolbars(self) -> None:
        top = QToolBar("主工具栏")
        top.setObjectName("topBar")
        top.setMovable(False)
        top.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(top)

        self.btn_sidebar = QToolButton()
        self.btn_sidebar.setText("◧  列表")
        self.btn_sidebar.setCheckable(True)
        self.btn_sidebar.setChecked(True)
        self.btn_sidebar.setToolTip("显示 / 隐藏左侧病例列表　(Ctrl+B)")
        self.btn_sidebar.clicked.connect(self.toggle_sidebar)
        top.addWidget(self.btn_sidebar)
        top.addSeparator()

        for a in (self.act_import, self.act_roster, self.act_save):
            top.addAction(a)
        top.addSeparator()

        lbl0 = QLabel("  片型  ")
        lbl0.setStyleSheet(f"color:{T.NIBI};")
        top.addWidget(lbl0)
        self.mode_combo = QComboBox()
        self.mode_combo.setMinimumWidth(150)
        for mid, label in MODE_LABEL.items():
            self.mode_combo.addItem(label, mid)
        self.mode_combo.setToolTip(
            "全景片：一张片 = 一个病人。\n"
            "根尖片：一个文件夹 = 一个病人，里面是他的多张小牙片；\n"
            "　　　　「全口最重位点」跨该病人的所有片子取，导出也按病人汇总。"
        )
        self.mode_combo.currentIndexChanged.connect(self._on_mode_combo)
        top.addWidget(self.mode_combo)
        top.addSeparator()

        lbl = QLabel("  计算公式  ")
        lbl.setStyleSheet(f"color:{T.NIBI};")
        top.addWidget(lbl)
        self.formula_combo = QComboBox()
        self.formula_combo.setMinimumWidth(330)
        for fid, label in formula_choices():
            self.formula_combo.addItem(label, fid)
        self.formula_combo.setToolTip(
            "四个公式共用每邻面的 CEJ、CEJ下2mm、AC、根尖四个坐标。\n"
            "①②以 CEJ 为起点；③④需补标 CEJ下2mm。切换后全项目自动重算。"
        )
        self.formula_combo.currentIndexChanged.connect(self._on_formula_combo)
        top.addWidget(self.formula_combo)
        top.addSeparator()
        top.addAction(self.act_recalc)

        export_menu = QMenu(self)
        for a in (self.act_csv, self.act_xlsx, self.act_json):
            export_menu.addAction(a)
        top.addWidget(self._menu_button("导出  ▾", export_menu, "导出测量结果"))

        # ── 底部：主线操作 ────────────────────────────────────────
        bot = QToolBar("操作栏")
        bot.setObjectName("bottomBar")
        bot.setMovable(False)
        bot.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(Qt.ToolBarArea.BottomToolBarArea, bot)

        self.btn_hand = QToolButton()
        self.btn_hand.setText("抓手  (H)")
        self.btn_hand.setCheckable(True)
        self.btn_hand.setToolTip("左键拖动平移；中键拖动、触控板双指滑动也可平移；双击牙框放大标注")
        self.btn_hand.toggled.connect(self._toggle_hand)
        bot.addWidget(self.btn_hand)
        self.btn_pick = QToolButton()
        self.btn_pick.setText("画框选牙  (T)")
        self.btn_pick.setCheckable(True)
        self.btn_pick.setToolTip("拖出方框把可疑牙位框住，务必含牙冠 + 牙根 + 根尖；牙框在项目内保存，导出仅含当前标点")
        self.btn_pick.toggled.connect(self._toggle_pick)
        bot.addWidget(self.btn_pick)
        bot.addAction(self.act_undo_box)
        self._set_view_tool(MODE_HAND)

        self.btn_annotate = QToolButton()
        self.btn_annotate.setText("开始标定  (Enter)")
        self.btn_annotate.clicked.connect(self.start_annotation)
        bot.addWidget(self.btn_annotate)
        self.btn_auto_segment = QToolButton()
        self.btn_auto_segment.setText("自动分割牙齿")
        self.btn_auto_segment.setToolTip("仅分割牙齿并保存轮廓和牙框；现有标点保持原样")
        self.btn_auto_segment.clicked.connect(self.start_auto_segmentation)
        bot.addWidget(self.btn_auto_segment)
        self.btn_auto_annotate = QToolButton()
        self.btn_auto_annotate.setText("自动标注")
        self.btn_auto_annotate.setToolTip("在当前牙框上识别 CEJ、AC、根尖候选；不重新分割，不填写 CEJ下2mm")
        self.btn_auto_annotate.clicked.connect(self.start_auto_annotation)
        bot.addWidget(self.btn_auto_annotate)
        self.btn_auto = self.btn_auto_annotate  # Compatibility for existing UI integrations.
        self.btn_cancel_auto = QToolButton()
        self.btn_cancel_auto.setText("取消自动任务")
        self.btn_cancel_auto.clicked.connect(self._ai.cancel)
        self.btn_cancel_auto.setVisible(False)
        bot.addWidget(self.btn_cancel_auto)
        bot.addSeparator()

        bot.addWidget(self._menu_button("看片调节  ▾", self._build_adjust_menu(),
                                        "亮度 / 对比 / 增强 / 反相"))
        bot.addWidget(self._menu_button("图层  ▾", self._build_layer_menu(),
                                        "曲线 / 标签 / 长轴 / 选框 的显示开关"))

        spacer = QWidget()
        spacer.setSizePolicy(spacer.sizePolicy().horizontalPolicy().Expanding,
                             spacer.sizePolicy().verticalPolicy().Preferred)
        bot.addWidget(spacer)

        self.btn_flag = QToolButton()
        self.btn_flag.setText("标记存疑  (F)")
        self.btn_flag.clicked.connect(self.toggle_flag)
        bot.addWidget(self.btn_flag)

        self.btn_done = QToolButton()
        self.btn_done.setText("完成本例并下一张  (Ctrl+Enter)")
        self.btn_done.setStyleSheet(
            f"QToolButton{{background:{T.AI};color:#FFFFFF;font-weight:600;"
            f"border:1px solid {T.AI};border-radius:6px;padding:5px 14px;}}"
            f"QToolButton:hover{{background:{T.AI_HOVER};border-color:{T.AI_HOVER};}}"
            f"QToolButton:disabled{{background:{T.BORDER_SOFT};color:{T.USUZUMI};"
            f"border-color:{T.BORDER_SOFT};}}"
        )
        self.btn_done.clicked.connect(self.finish_case)
        bot.addWidget(self.btn_done)

    def _menu_button(self, text: str, menu: QMenu, tip: str = "") -> QToolButton:
        b = QToolButton()
        b.setText(text)
        b.setMenu(menu)
        b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        if tip:
            b.setToolTip(tip)
        return b

    def _build_adjust_menu(self) -> QMenu:
        """看片调节收进弹出面板 —— 底部栏不再被一堆滑块撑爆。"""
        panel = QWidget()
        grid = QGridLayout(panel)
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        self.sl_bright = self._slider(-100, 100)
        self.sl_contrast = self._slider(-100, 100)
        grid.addWidget(QLabel("亮度"), 0, 0)
        grid.addWidget(self.sl_bright, 0, 1)
        grid.addWidget(QLabel("对比度"), 1, 0)
        grid.addWidget(self.sl_contrast, 1, 1)

        self.cb_clahe = QCheckBox("局部增强 (CLAHE)")
        self.cb_clahe.setToolTip("全景片明暗不均时很有效，能把骨嵴边缘拉出来")
        self.cb_clahe.toggled.connect(self._apply_adjust)
        self.cb_invert = QCheckBox("反相")
        self.cb_invert.toggled.connect(self._apply_adjust)
        grid.addWidget(self.cb_clahe, 2, 0, 1, 2)
        grid.addWidget(self.cb_invert, 3, 0, 1, 2)

        reset = QToolButton()
        reset.setText("重置")
        reset.clicked.connect(self._reset_adjust)
        grid.addWidget(reset, 4, 0, 1, 2)

        menu = QMenu(self)
        act = QWidgetAction(menu)
        act.setDefaultWidget(panel)
        menu.addAction(act)
        return menu

    def _build_layer_menu(self) -> QMenu:
        menu = QMenu(self)
        self._layer_acts = {}
        for key, text, default in (
            ("labels", "点标签 / 牙位", True),
            ("axis", "牙长轴与投影", True),
            ("roi", "选牙方框", True),
            ("segmentation", "自动分割轮廓", True),
        ):
            a = QAction(text, self)
            a.setCheckable(True)
            a.setChecked(default)
            a.toggled.connect(self._apply_layers)
            menu.addAction(a)
            self._layer_acts[key] = a
        return menu

    def _slider(self, lo: int, hi: int) -> QSlider:
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(lo, hi)
        s.setValue(0)
        s.setMinimumWidth(150)
        s.valueChanged.connect(self._apply_adjust)
        return s

    def _build_shortcuts(self) -> None:
        for text, slot, key in (
            ("pick", lambda: self.btn_pick.toggle(), "T"),
            ("hand", lambda: self._set_view_tool(MODE_HAND), "H"),
            ("annotate", self.start_annotation, "Return"),
            ("flag", self.toggle_flag, "F"),
            ("finish", self.finish_case, "Ctrl+Return"),
            ("next", lambda: self.jump(1), "Ctrl+Right"),
            ("prev", lambda: self.jump(-1), "Ctrl+Left"),
        ):
            a = QAction(text, self)
            a.setShortcut(QKeySequence(key))
            a.triggered.connect(slot)
            self.addAction(a)

    # ══ 侧栏 ════════════════════════════════════════════════════════
    def toggle_sidebar(self, *_):
        show = not self.cases.isVisible()
        if not show:
            self._sidebar_width = max(200, self.cases.width())
        self.cases.setVisible(show)
        if show:
            sizes = self.splitter.sizes()
            total = sum(sizes)
            self.splitter.setSizes(
                [self._sidebar_width, total - self._sidebar_width - sizes[2], sizes[2]]
            )
        for w in (self.btn_sidebar, self.act_sidebar):
            w.blockSignals(True)
            w.setChecked(show)
            w.blockSignals(False)

    # ══ 项目 ════════════════════════════════════════════════════════
    def new_project(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择一个空文件夹作为项目目录")
        if not d:
            return
        self._load_project(Project.create(Path(d)))
        QMessageBox.information(
            self, "项目已创建",
            "接下来把全景片一次性拖进窗口（或用「批量导入全景片」），\n"
            "软件会自动去重、按文件名自然排序（1, 2, 10 而不是 1, 10, 2）。",
        )

    def open_project(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "打开项目文件夹")
        if d:
            self._load_project(Project.open(Path(d)))

    def _load_project(self, project: Project) -> None:
        if self._ai_busy:
            return
        self.save_current(silent=True)
        self.project = project
        self.entry = None
        self.ann = None
        self._gray = None
        self.view.set_case(None, None)
        self.inspector.set_case(None, project.grading)
        self.cases.set_project(project)
        self._sync_formula_widgets(project.settings.formula_id)
        self._sync_mode_widget(project.settings.mode)
        self.setWindowTitle(f"{self._mode_title} — {project.root}")
        QSettings(ORG, APP).setValue("last_project", str(project.root))
        self._update_enabled()
        first = project.next_unfinished()
        if first:
            self.cases.select(first)
            self.open_case(first)

    def import_images(self) -> None:
        if self.project is None:
            QMessageBox.warning(self, "请先打开项目", "请先「新建项目」或「打开项目」。")
            return
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择全景片（可多选）", "",
            "图像 (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp);;所有文件 (*)",
        )
        if not files:
            d = QFileDialog.getExistingDirectory(self, "或选择一个包含全景片的文件夹")
            if not d:
                return
            files = [d]
        self._do_import([Path(f) for f in files])

    def _do_import(self, paths: list[Path]) -> None:
        added, skipped = self.project.import_paths(paths)
        self.cases.refresh()
        self._update_enabled()
        msg = f"新增 {len(added)} 张。"
        if skipped:
            msg += f"\n\n跳过 {len(skipped)} 项：\n" + "\n".join(skipped[:12])
            if len(skipped) > 12:
                msg += f"\n…另有 {len(skipped) - 12} 项"
        QMessageBox.information(self, "导入完成", msg)
        if added and self.entry is None:
            self.cases.select(added[0])
            self.open_case(added[0])

    def import_roster(self) -> None:
        if self.project is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "选择名册文件", "", "表格 (*.csv *.xlsx *.xlsm);;所有文件 (*)"
        )
        if not path:
            return
        try:
            rows = roster_mod.read_roster(Path(path))
        except (ValueError, OSError) as e:
            QMessageBox.critical(self, "名册读取失败", str(e))
            return
        if not rows:
            QMessageBox.warning(self, "名册为空", "没有读到有效数据行。")
            return

        # 下面会逐个从磁盘读写标注，必须先把当前病例落盘 ——
        # 否则内存里刚标好、还没保存的点会被磁盘上的旧内容覆盖掉。
        self.save_current(silent=True)

        report = roster_mod.match([c.case_id for c in self.project.cases], rows)
        applied = 0
        for case_id, row in report.matched:
            entry = self.project.find(case_id)
            if entry is None:
                continue
            # 当前病例始终更新界面持有的同一份标注；否则刷新/切换时
            # save_current 会把导入前的年龄、性别写回磁盘，覆盖名册。
            ann = (self.ann if entry is self.entry and self.ann is not None
                   else self.project.load_annotation(entry))
            changed = False
            if row.age is not None and ann.patient.age != row.age:
                ann.patient.age, changed = row.age, True
            if row.sex and ann.patient.sex != row.sex:
                ann.patient.sex, changed = row.sex, True
            if row.note and ann.patient.note != row.note:
                ann.patient.note, changed = row.note, True
            if row.id and not ann.patient.id:
                ann.patient.id, changed = row.id, True
            if changed:
                self.project.save_annotation(entry, ann)
                applied += 1

        detail = report.summary() + f"\n实际写入 {applied} 例。"
        if report.unmatched_cases:
            detail += "\n\n未匹配的病例：\n" + "、".join(report.unmatched_cases[:20])
            if len(report.unmatched_cases) > 20:
                detail += f" …等 {len(report.unmatched_cases)} 例"
        if self.entry is not None:
            self._refresh_all()
        self.cases.refresh(self.entry)
        QMessageBox.information(self, "名册匹配结果", detail)

    # ══ 病例 ════════════════════════════════════════════════════════
    def open_case(self, entry: CaseEntry, force: bool = False) -> None:
        if self._ai_busy:
            return
        if self.project is None or (self.entry is entry and not force):
            return
        self.save_current(silent=True)

        self.entry = entry
        self.ann = self.project.load_annotation(entry)
        path = self.project.image_path(entry)
        self._gray = load_gray(path)
        if self._gray is None:
            QMessageBox.warning(self, "读取失败", f"无法读取图像：\n{path}")
            self.view.set_case(None, None)
            return

        self.ann.image_width, self.ann.image_height = (
            self._gray.shape[1], self._gray.shape[0]
        )
        if not self.ann.patient.id:
            self.ann.patient.id = entry.case_id
        self._t0 = time.monotonic()
        self._dirty = False

        self._refresh_all(reset_view=True)
        self._update_enabled()
        self._set_view_tool(MODE_HAND)
        self._set_hint("可自动分割牙齿；双击牙框放大标注，抓手拖动看片，按 T 手工重画牙框。")

    def _refresh_all(self, reset_view: bool = False) -> None:
        if self.ann is None or self._gray is None:
            return
        f = get_formula(self.ann.formula_id)
        fcfg = self.project.grading.formula_config()
        self.view.set_case(
            apply_adjust(self._gray, self._adjust), self.ann, f, fcfg,
            keep_view=not reset_view,
        )
        self.inspector.set_case(self.ann, self.project.grading)
        self.inspector.set_patient_worst(self._patient_worst())
        self._update_enabled()

    def _patient_worst(self) -> tuple[str, float] | None:
        """根尖片模式下，同一病人跨全部片子的最重位点。

        「全口最重」本来就该跨这个病人的所有小牙片取，而不是每张片各算各的。
        """
        if not (self.project and self.project.periapical and self.entry):
            return None
        best = None
        for film in self.project.siblings(self.entry):
            ann = self.ann if film is self.entry else self.project.load_annotation(film)
            r = ann.compute(self.project.grading)
            if r.worst_ratio is None:
                continue
            if best is None or r.worst_ratio > best[1]:
                best = (film.display, r.worst_ratio)
        return best

    def save_current(self, silent: bool = False) -> None:
        if self.project is None or self.entry is None or self.ann is None:
            return
        if not self._dirty and not silent:
            self._set_hint("没有需要保存的改动")
            return
        if self._t0 is not None:
            self.ann.duration_s += time.monotonic() - self._t0
            self._t0 = time.monotonic()
        if self.ann.teeth and self.entry.status == STATUS_PENDING:
            self.project.set_status(self.entry, STATUS_IN_PROGRESS)
        self.project.save_annotation(self.entry, self.ann)
        self._dirty = False
        self.cases.refresh(self.entry)
        if not silent:
            self._set_hint("已保存")

    def _mark_dirty(self) -> None:
        self._dirty = True

    def _on_patient_changed(self) -> None:
        self._mark_dirty()
        self._sync_patient_info()
        self.cases.refresh(self.entry)

    def _sync_patient_info(self) -> None:
        """根尖片模式下，年龄/性别/病例号自动同步给同一病人的其他片子。

        一个病人可能有十几张小牙片，逐张填年龄既费事又容易填不一致，
        而年龄不一致会让「骨吸收年龄比」在同一个病人身上算出不同的值。
        """
        if not (self.project and self.project.periapical and self.entry and self.ann):
            return
        src = self.ann.patient
        for film in self.project.siblings(self.entry):
            if film is self.entry:
                continue
            ann = self.project.load_annotation(film)
            if (ann.patient.age == src.age and ann.patient.sex == src.sex
                    and ann.patient.id == src.id):
                continue
            ann.patient.age, ann.patient.sex, ann.patient.id = src.age, src.sex, src.id
            self.project.save_annotation(film, ann)

    def finish_case(self) -> None:
        if self.entry is None or self.ann is None:
            return
        if self.ann.annotated_tooth_count == 0:
            r = QMessageBox.question(
                self, "尚未标定",
                "这张片子还没有任何标定完整的牙位。仍然标为「已完成」吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if r != QMessageBox.StandardButton.Yes:
                return
        self._dirty = True
        self.save_current(silent=True)
        nxt = self.project.next_unfinished(self.entry)
        self.project.set_status(self.entry, STATUS_DONE)
        self.cases.refresh()
        cnt = self.project.counts()
        done_id = self.entry.case_id
        if nxt is not None:
            self.cases.select(nxt)
            self.open_case(nxt)
            self._set_hint(f"✓ {done_id} 已完成　·　已完成 {cnt[STATUS_DONE]} 张，"
                           f"剩余 {cnt['remaining']} 张")
        else:
            QMessageBox.information(self, "全部完成", "这批片子已经全部标注完毕。")

    def toggle_flag(self) -> None:
        if self.entry is None:
            return
        new = STATUS_PENDING if self.entry.status == STATUS_FLAGGED else STATUS_FLAGGED
        self.project.set_status(self.entry, new)
        self.cases.refresh(self.entry)
        self._set_hint("已标记存疑" if new == STATUS_FLAGGED else "已取消标记")

    def jump(self, delta: int) -> None:
        if self.project is None or self.entry is None:
            return
        cases = self.project.sorted_cases()
        i = cases.index(self.entry) + delta
        if 0 <= i < len(cases):
            self.cases.select(cases[i])
            self.open_case(cases[i])

    # ══ 公式 ════════════════════════════════════════════════════════
    def _on_formula_combo(self, *_):
        fid = self.formula_combo.currentData()
        if fid:
            self.set_formula(fid)

    def set_formula(self, fid: str) -> None:
        """切换公式。**项目级**生效 —— 一批研究数据必须口径一致。

        因为文件里存的是坐标不是结果，切换后所有已标病例的比值会立即按新公式
        重算，不需要重标任何一个点。
        """
        if self.project is None or fid not in FORMULAS:
            return
        if self.project.settings.formula_id == fid and (
            self.ann is None or self.ann.formula_id == fid
        ):
            return
        self.project.settings.formula_id = fid
        self.project.save()
        if self.ann is not None:
            self.ann.formula_id = fid
            self._mark_dirty()
        self._sync_formula_widgets(fid)
        self._refresh_all()
        n = len([c for c in self.project.cases if c.annotated_teeth])
        self._set_hint(f"已切换为「{FORMULAS[fid].label}」，"
                       f"{n} 个已标病例的比值已按新公式重算，标定点未改动")

    # ══ 列表右键操作 ════════════════════════════════════════════════
    def rename_case(self, entry: CaseEntry) -> None:
        name, ok = QInputDialog.getText(
            self, "重命名", "列表里显示的名字：", text=entry.display
        )
        if not ok:
            return
        self.project.rename(entry, name)
        self.cases.refresh(self.entry)
        self._set_hint(f"已重命名为「{entry.display}」")

    def regroup_cases(self, entries: list) -> None:
        """把选中的多张根尖片归到同一个病人下。

        批量导入时若文件夹结构不规整（比如一个病人的片子散在几个文件夹里），
        用这个手工并组，之后「全口最重位点」就会跨这些片子取。
        """
        if not entries or self.project is None:
            return
        default = entries[0].patient_key
        key, ok = QInputDialog.getText(
            self, "归为同一个病人",
            f"把选中的 {len(entries)} 张片子归到哪个病人下？", text=default
        )
        if not ok or not key.strip():
            return
        for e in entries:
            self.project.set_patient_key(e, key)
        self.cases.refresh(self.entry)
        self._set_hint(f"已把 {len(entries)} 张片子归到病人「{key.strip()}」")

    def delete_cases(self, entries: list) -> None:
        if not entries or self.project is None:
            return
        names = "、".join(e.display for e in entries[:6])
        if len(entries) > 6:
            names += f" …等 {len(entries)} 张"

        box = QMessageBox(self)
        box.setWindowTitle("从项目移除")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(f"要移除：{names}")
        box.setInformativeText(
            "「仅移出列表」保留项目里的图片与标注文件，重新导入即可接上；\n"
            "「连同文件删除」会真正删掉项目 images/ 里的图片和对应标注，不可撤销。\n\n"
            "（用「引用模式」导入的原图永远不会被删 —— 那是你自己的原始数据。）"
        )
        b_soft = box.addButton("仅移出列表", QMessageBox.ButtonRole.AcceptRole)
        b_hard = box.addButton("连同文件删除", QMessageBox.ButtonRole.DestructiveRole)
        b_cancel = box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(b_cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked is b_cancel:
            return
        hard = clicked is b_hard
        if hard:
            r = QMessageBox.question(
                self, "再次确认",
                f"确定要**永久删除** {len(entries)} 张片子及其标注吗？此操作不可撤销。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if r != QMessageBox.StandardButton.Yes:
                return

        removing_current = self.entry in entries
        if removing_current:
            self._dirty = False           # 别把待删的病例又存回去
            nxt = self.project.next_unfinished(self.entry)
            if nxt in entries:
                nxt = None
        for e in entries:
            self.project.remove_case(e, delete_files=hard)
        if removing_current:
            self.entry = None
            self.ann = None
            self._gray = None
            self.view.set_case(None, None)
            self.inspector.set_case(None, self.project.grading)
        self.cases.refresh()
        self._update_enabled()
        if removing_current:
            nxt = nxt or (self.project.sorted_cases()[0] if self.project.cases else None)
            if nxt is not None:
                self.cases.select(nxt)
                self.open_case(nxt)
        self._set_hint(f"已移除 {len(entries)} 张" + ("（含文件）" if hard else "（文件保留）"))

    def reveal_case(self, entry: CaseEntry) -> None:
        import subprocess
        path = self.project.image_path(entry)
        try:
            subprocess.Popen(["explorer", "/select,", str(path)])
        except OSError:
            QMessageBox.information(self, "路径", str(path))

    # ══ 片型 ════════════════════════════════════════════════════════
    def _on_mode_combo(self, *_):
        mid = self.mode_combo.currentData()
        if self.project is None or mid == self.project.settings.mode:
            return
        n = len(self.project.cases)
        if n:
            r = QMessageBox.question(
                self, "切换片型",
                f"当前项目里已有 {n} 张片子。\n\n"
                "切换片型只改变**分组与导出方式**，不动任何图片和标定点：\n"
                "　· 全景片：一张片 = 一个病人\n"
                "　· 根尖片：一个文件夹 = 一个病人，最重位点跨该病人所有片子取\n\n"
                "已导入的片子会按各自的来源文件夹重新归组。要继续吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if r != QMessageBox.StandardButton.Yes:
                self._sync_mode_widget(self.project.settings.mode)
                return
        self.set_mode(mid)

    def set_mode(self, mid: str) -> None:
        if self.project is None or mid not in MODE_LABEL:
            return
        self.project.settings.mode = mid
        self.project.save()
        self._sync_mode_widget(mid)
        self.cases.refresh(self.entry)
        self.inspector.set_periapical(self.project.periapical)
        self._refresh_all()
        self._set_hint(f"片型已切换为「{MODE_LABEL[mid]}」")

    def _sync_mode_widget(self, mid: str) -> None:
        i = self.mode_combo.findData(mid)
        if i >= 0 and i != self.mode_combo.currentIndex():
            self.mode_combo.blockSignals(True)
            self.mode_combo.setCurrentIndex(i)
            self.mode_combo.blockSignals(False)
        self.cases.set_periapical(mid == MODE_PERIAPICAL)
        self.inspector.set_periapical(mid == MODE_PERIAPICAL)

    def _sync_formula_widgets(self, fid: str) -> None:
        for w in (self.formula_combo, self.inspector.formula_box):
            i = w.findData(fid)
            if i >= 0 and i != w.currentIndex():
                w.blockSignals(True)
                w.setCurrentIndex(i)
                w.blockSignals(False)

    # ══ 画框选牙 / 标定 ═════════════════════════════════════════════
    def _teeth_snapshot(self, input_sha256: str) -> dict:
        teeth = []
        for tooth in self.ann.teeth:
            if tooth.roi is None:
                continue
            x, y, w, h = tooth.roi
            teeth.append({
                "source_tooth_id": tooth.tooth_id, "instance_id": tooth.tooth_id,
                "fdi": tooth.fdi, "origin": tooth.origin,
                "score": tooth.segmentation.get("score"),
                "bbox_xyxy": [x, y, x+w, y+h],
                "contours": deepcopy(tooth.segmentation.get("contours", [])),
            })
        return {"schema_version": 1,
                "image": {"width": self.ann.image_width, "height": self.ann.image_height,
                          "sha256": input_sha256}, "teeth": teeth}

    def start_auto_segmentation(self) -> None:
        self._start_ai_operation("segmentation")

    def start_auto_annotation(self) -> None:
        self._start_ai_operation("keypoints")

    def _start_ai_operation(self, mode: str) -> None:
        if (self._ai_busy or self.project is None or self.entry is None
                or self.ann is None or self._gray is None):
            return
        if mode == "keypoints" and not any(t.roi is not None for t in self.ann.teeth):
            self._set_hint("请先手动画框选牙或点击「自动分割牙齿」，再执行「自动标注」。")
            return
        self.save_current(silent=True)
        run_dir = self.project.root / "runs" / uuid.uuid4().hex
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
            input_path = run_dir / "input.png"
            if not imwrite_unicode(input_path, self._gray):
                raise OSError("无法保存本次自动标注的原始图像")
            input_sha256 = hashlib.sha256(input_path.read_bytes()).hexdigest()
            snapshot, teeth_path, teeth_sha256 = None, None, None
            if mode == "keypoints":
                snapshot = self._teeth_snapshot(input_sha256)
                teeth_path = run_dir / "teeth.json"
                teeth_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
                teeth_sha256 = hashlib.sha256(teeth_path.read_bytes()).hexdigest()
            self._ai_context = {
                "project": self.project, "entry": self.entry, "ann": self.ann,
                "run_dir": run_dir, "input_path": input_path,
                "preconversion": "opencv_grayscale_uint8", "mode": mode,
                "input_sha256": input_sha256, "teeth_snapshot": snapshot,
                "teeth_path": teeth_path, "teeth_sha256": teeth_sha256,
            }
            self._ai_busy = True
            self._set_view_tool(MODE_HAND)
            self._update_enabled()
            if mode == "segmentation":
                self._set_hint("正在载入模型并自动分割牙齿…")
                self._ai.start(input_path, run_dir / "output", mode="segmentation")
            else:
                self._set_hint(f"正在当前 {len(snapshot['teeth'])} 个牙框上识别三点候选…")
                self._ai.start(input_path, run_dir / "output", mode="keypoints", teeth_path=teeth_path)
        except (OSError, RuntimeError, ValueError) as exc:
            self._ai_failed(str(exc))

    def _ai_progress(self, event: dict) -> None:
        message = event.get("message") or {
            "segmentation": "正在分割牙齿", "keypoints": "正在识别三点候选",
            "loading": "正在载入模型", "export": "正在还原坐标并保存结果",
        }.get(event.get("stage"), "正在自动标注")
        total = event.get("total")
        suffix = f"（{event.get('current', 0)}/{total}）" if total else ""
        self._set_hint(str(message) + suffix)

    def _ai_finish(self) -> None:
        self._ai_busy = False
        self._ai_context = None
        self._update_enabled()

    def _ai_completed(self, result_path: str) -> None:
        context = self._ai_context
        if context is None:
            return
        project, entry, ann = context["project"], context["entry"], context["ann"]
        input_path, preconversion, mode = context["input_path"], context["preconversion"], context["mode"]
        try:
            if project is not self.project or entry is not self.entry or ann is not self.ann:
                raise RuntimeError("当前病例已切换，自动结果已留在 runs 文件夹，未应用到其他病例")
            from ..core.ai_merge import merge_ai_result
            with Path(result_path).open(encoding="utf-8") as stream:
                result = json.load(stream)
            with input_path.open("rb") as stream:
                input_sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
            image = result.get("image", {})
            if image.get("sha256") != input_sha256 or input_sha256 != context["input_sha256"]:
                raise ValueError("自动结果与本次输入图像的 SHA256 不一致，已拒绝应用")
            if image.get("coordinate_space") != "canonical_image_pixel_centers":
                raise ValueError("自动结果的坐标空间不受支持，已拒绝应用")
            if result.get("mode") != mode:
                raise ValueError("自动结果与本次请求的操作不一致，已拒绝应用")
            if mode == "segmentation" and any(t.get("surfaces") for t in result.get("teeth", [])):
                raise ValueError("自动分割仅接受牙齿轮廓和牙框，不能写入自动标点")
            if mode == "keypoints":
                snapshot = context["teeth_snapshot"]
                if self._teeth_snapshot(input_sha256) != snapshot:
                    raise ValueError("当前牙齿身份或牙框已改变，自动标注结果已保留但未应用")
                if json.loads(context["teeth_path"].read_text(encoding="utf-8")) != snapshot:
                    raise ValueError("本次牙框输入快照已改变，已拒绝应用")
                if (hashlib.sha256(context["teeth_path"].read_bytes()).hexdigest() != context["teeth_sha256"]
                        or result.get("teeth_source", {}).get("sha256") != context["teeth_sha256"]):
                    raise ValueError("自动标注结果与本次牙框快照的 SHA256 不一致，已拒绝应用")
                expected = {t["source_tooth_id"]: t for t in snapshot["teeth"]}
                predictions = result.get("teeth", [])
                ids = [t.get("source_tooth_id") for t in predictions]
                if len(ids) != len(expected) or set(ids) != set(expected):
                    raise ValueError("自动标注结果未完整对应本次牙框，已拒绝应用")
                for prediction in predictions:
                    if prediction.get("bbox_xyxy") != expected[prediction["source_tooth_id"]]["bbox_xyxy"]:
                        raise ValueError("自动标注结果的牙框与输入快照不一致，已拒绝应用")
            result["result_ref"] = Path(result_path).relative_to(project.root).as_posix()
            result["source_case"] = {"image": entry.image, "sha1": entry.sha1}
            result["analysis_input"] = {"sha256": input_sha256, "preconversion": preconversion,
                                        "display_adjust_used": False,
                                        "input_ref": input_path.relative_to(project.root).as_posix()}
            if mode == "keypoints":
                result["analysis_input"].update({
                    "teeth_ref": context["teeth_path"].relative_to(project.root).as_posix(),
                    "teeth_sha256": context["teeth_sha256"],
                })
            summary = merge_ai_result(ann, result)
            if mode == "keypoints":
                constrain_pending_candidates(ann)
            if (summary["added_teeth"] or summary["points_added"]) and entry.status != STATUS_FLAGGED:
                project.set_status(entry, STATUS_IN_PROGRESS)
            self._mark_dirty()
            self.save_current(silent=True)
            self._refresh_all()
            if mode == "segmentation":
                self._set_hint(f"分割已保存：{summary['added_teeth'] + summary['matched_teeth']} 颗牙。"
                    "可点击「自动标注」生成三点候选，或双击牙框手工标四点。")
            else:
                self._set_hint(
                    f"自动标注已保存：补入 {summary['points_added']} 个候选点；"
                    f"{summary['teeth_without_points']} 颗牙未检出三点。"
                    "有轮廓时按轮廓约束候选；解剖位置仍需复核，双击牙框可补点。"
                )
        except Exception as exc:
            self._ai_failed(f"自动结果无法应用：{exc}")
            return
        self._ai_finish()

    def _ai_failed(self, message: str) -> None:
        self._ai_finish()
        self._set_hint(message)
        QMessageBox.warning(self, "自动任务未完成", message)

    def _ai_cancelled(self) -> None:
        self._ai_finish()
        self._set_hint("已取消自动任务，现有标注保持原样")

    def _toggle_pick(self, on: bool) -> None:
        self._set_view_tool(MODE_PICK if on else MODE_HAND)

    def _toggle_hand(self, on: bool) -> None:
        self._set_view_tool(MODE_HAND if on else MODE_VIEW)

    def _set_view_tool(self, mode: str) -> None:
        for button, active in ((self.btn_pick, mode == MODE_PICK), (self.btn_hand, mode == MODE_HAND)):
            button.blockSignals(True)
            button.setChecked(active)
            button.blockSignals(False)
        self.view.cancel_box()
        self.view.set_mode(mode)
        self._set_hint(self._pick_hint() if mode == MODE_PICK else "抓手拖动看片；双击牙框放大标注。")

    def _pick_hint(self) -> str:
        n = len(self.ann.teeth) if self.ann else 0
        base = "画框选牙：拖出方框把整颗牙框住（务必含牙冠 + 牙根 + 根尖）。"
        return base + f"　已有 {n} 颗；重画覆盖旧框，Ctrl+Z 撤销框选。"

    def _on_box_drawn(self, rect) -> None:
        """Replace a related rectangle while preserving tooth identity and all points."""
        if self._ai_busy or self.ann is None or self._gray is None:
            return
        roi = (rect.x(), rect.y(), rect.width(), rect.height())
        candidates = replacement_candidates(self.ann, roi)
        target = candidates[0] if len(candidates) == 1 else None
        if len(candidates) > 1:
            menu = QMenu(self)
            original_ann = self.ann
            for i, candidate in enumerate(candidates):
                action = menu.addAction(f"替换方框 {chr(65+i) if i < 26 else i+1} · 牙位 {candidate.name}")
                action.triggered.connect(lambda _checked=False, t=candidate:
                    self._replace_drawn_box(original_ann, roi, t))
            menu.addSeparator()
            menu.addAction("取消")
            menu.aboutToHide.connect(menu.deleteLater)
            menu.popup(self.view.mapToGlobal(self.view.rect().center()))
            return
        if target is not None:
            self._replace_drawn_box(self.ann, roi, target)
            return
        h, w = self._gray.shape[:2]
        c = rect.center()
        fdi_guess = guess_fdi(c.x(), c.y(), w, h, self._occlusal_y())
        fdi, ok = QInputDialog.getInt(
            self, "牙位号",
            f"这颗牙的 FDI 牙位号（推测：{fdi_guess}）：\n"
            "直接回车接受推测值，或输入正确的牙位号。",
            fdi_guess or 16, 11, 48,
        )
        if not ok:
            return
        edit_box(self.ann, roi, fdi=fdi)
        self._box_edit_finished(self._pick_hint())

    def _replace_drawn_box(self, original_ann, roi, target) -> None:
        if self._ai_busy or self.ann is not original_ann or target not in self.ann.teeth:
            return
        edit_box(self.ann, roi, target)
        self._box_edit_finished(f"已替换牙位 {target.name} 的框，原有标点保留；Ctrl+Z 可找回原框。")

    def _box_edit_finished(self, hint: str) -> None:
        self._mark_dirty()
        self.save_current(silent=True)
        self._refresh_all()
        self._update_enabled()
        self._set_hint(hint)

    def undo_box_edit(self) -> None:
        if self.ann is not None and not self._ai_busy and undo_box(self.ann):
            self._box_edit_finished("已恢复原框；标点保留。")

    def snap_candidates(self) -> None:
        if self.ann is None or self._ai_busy:
            return
        stats = constrain_pending_candidates(self.ann)
        self._box_edit_finished(f"已将 {stats['projected']} 个未修改候选贴合轮廓，"
            f"最大移动 {stats['max_distance_px']:.1f} 像素；{stats['missing_contour']} 个缺轮廓未移动。"
            "手工点保持原样；贴线结果仍需复核。")

    def _occlusal_y(self) -> float:
        """咬合平面的粗略高度，只用于推测牙位号的上下颌归属。"""
        return (self._gray.shape[0] / 2) if self._gray is not None else 0.0

    def start_annotation(self, tooth=None) -> None:
        if self._ai_busy or self.ann is None or self._gray is None:
            return
        if not self.ann.teeth:
            QMessageBox.information(
                self, "先画框选牙",
                "请先点击自动分割按钮，或按 T 手动画框选择牙位。\n\n"
                "画框时务必把整颗牙框进去（牙冠 + 牙根 + 根尖），放大标点时才不会缺根尖。",
            )
            return
        dlg = ToothDialog(
            apply_adjust(self._gray, self._adjust), self.ann, list(self.ann.teeth),
            get_formula(self.ann.formula_id),
            self.project.grading.formula_config(), self,
        )
        if isinstance(tooth, Tooth) and tooth in self.ann.teeth:
            dlg._goto_tooth(self.ann.teeth.index(tooth))
        if dlg.exec():
            self._mark_dirty()
            self.save_current(silent=True)
            self.btn_pick.setChecked(False)      # 标完回到全景浏览，看回显
        self._refresh_all()

    def _on_point_dragged(self, tooth: Tooth, site, role: str, pos) -> None:
        p = site.get(role)
        if p is None:
            return
        site.set(role, Pt(pos.x(), pos.y()))
        self._mark_dirty()
        self.inspector.refresh()

    def _remove_tooth(self, index: int) -> None:
        if self.ann is None:
            return
        tooth = next((t for t in self.ann.teeth if t.index == index), None)
        if tooth is None:
            return
        r = QMessageBox.question(
            self, "删除牙位",
            f"删除牙位 {tooth.name} 及其全部标定点？\n后续牙位的 P 编号会自动前移。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if r != QMessageBox.StandardButton.Yes:
            return
        self.ann.remove_tooth(tooth)
        self._mark_dirty()
        self._refresh_all()

    def clear_all_marks(self) -> None:
        """一键清空本片所有标记。两道确认 —— 手标的点重标代价很高。"""
        if self.ann is None or not self.ann.teeth:
            self._set_hint("本片没有任何标记")
            return
        n = len(self.ann.teeth)
        pts = sum(t.filled_count for t in self.ann.teeth)
        r = QMessageBox.question(
            self, "清空所有标记",
            f"要清空本片的 {n} 颗牙、{pts} 个标定点吗？\n\n"
            "清空后可以重新画框标定；旧标注会自动在 annotations/_backup/ 留一份备份。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if r != QMessageBox.StandardButton.Yes:
            return
        r2 = QMessageBox.warning(
            self, "再次确认",
            f"确定清空？{n} 颗牙的全部标定点都会被移除。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if r2 != QMessageBox.StandardButton.Yes:
            return
        self.ann.teeth.clear()
        self._mark_dirty()
        self.save_current(silent=True)
        self._refresh_all()
        self._set_hint(f"已清空 {n} 颗牙的标记（备份在 annotations/_backup/）")

    # ══ 看片调节 / 图层 ═════════════════════════════════════════════
    def _apply_adjust(self, *_):
        self._adjust.brightness = self.sl_bright.value()
        self._adjust.contrast = self.sl_contrast.value()
        self._adjust.clahe = self.cb_clahe.isChecked()
        self._adjust.invert = self.cb_invert.isChecked()
        if self._gray is not None:
            self.view.set_display_image(apply_adjust(self._gray, self._adjust))

    def _reset_adjust(self):
        for w in (self.sl_bright, self.sl_contrast):
            w.blockSignals(True)
            w.setValue(0)
            w.blockSignals(False)
        for w in (self.cb_clahe, self.cb_invert):
            w.blockSignals(True)
            w.setChecked(False)
            w.blockSignals(False)
        self._apply_adjust()

    def _apply_layers(self, *_):
        for key, act in self._layer_acts.items():
            setattr(self.view.layers, key, act.isChecked())
        self.view.refresh_overlay()

    def _on_mouse_moved(self, pos) -> None:
        self.pos_label.setText(f"({pos.x():.0f}, {pos.y():.0f})")

    def _set_hint(self, text: str) -> None:
        self.hint_label.setText(text)

    # ══ 重算 / 设置 / 导出 ══════════════════════════════════════════
    def recalculate_all(self) -> None:
        """换公式或改阈值后，对全部病例重算。

        因为 JSON 里存的是**坐标**而不是结果，这里只是重新读一遍、用新公式
        算一遍派生量并刷新缓存 —— 不需要重标任何一个点。
        """
        if self.project is None:
            return
        self.save_current(silent=True)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        n = 0
        for entry in self.project.sorted_cases():
            ann = self.project.load_annotation(entry)      # 已按项目公式赋 formula_id
            ann.compute(self.project.grading)
            entry.annotated_teeth = ann.annotated_tooth_count
            if ann.teeth:
                self.project.save_annotation(entry, ann)
            n += 1
        self.project.save()
        QApplication.restoreOverrideCursor()
        self.cases.refresh(self.entry)
        if self.entry:
            self.open_case(self.entry, force=True)
        QMessageBox.information(
            self, "重算完成",
            f"已按「{FORMULAS[self.project.settings.formula_id].label}」"
            f"与当前阈值重算 {n} 个病例。\n\n"
            "原始标定点未被修改 —— 这正是「存坐标不存结果」的好处：\n"
            "换公式只需切一下下拉框，不用重标。",
        )

    def open_settings(self) -> None:
        if self.project is None:
            return
        dlg = SettingsDialog(self.project.grading, self.project.settings, self)
        if dlg.exec():
            dlg.apply()
            self.project.save_grading()
            self.project.save()
            self._refresh_all()
            self._set_hint("设置已保存。如需对全部病例生效，请执行「工具 → 全部重算」。")

    def export_csv(self) -> None:
        if self.project is None:
            return
        self.save_current(silent=True)
        try:
            paths = exporter.export_csv(self.project, self.project.grading)
        except OSError as e:
            QMessageBox.critical(self, "导出失败", str(e))
            return
        QMessageBox.information(self, "导出完成",
                                "已导出：\n" + "\n".join(str(p) for p in paths))

    def export_excel(self) -> None:
        if self.project is None:
            return
        self.save_current(silent=True)
        try:
            p = exporter.export_excel(self.project, self.project.grading)
        except (OSError, ImportError) as e:
            QMessageBox.critical(self, "导出失败", str(e))
            return
        QMessageBox.information(self, "导出完成", f"已导出：\n{p}")

    def export_json(self) -> None:
        if self.project is None or self.entry is None:
            return
        self.save_current(silent=True)
        path, _ = QFileDialog.getSaveFileName(
            self, "导出当前病例 JSON",
            str(self.project.exports_dir / f"{self.entry.case_id}.json"), "JSON (*.json)",
        )
        if path:
            exporter.export_single_json(self.project, self.entry, Path(path))
            self._set_hint(f"已导出 {path}")

    # ══ 杂项 ════════════════════════════════════════════════════════
    def _update_enabled(self) -> None:
        available = not self._ai_busy
        has_proj = self.project is not None and available
        has_case = self.ann is not None and available
        for a in (self.act_import, self.act_roster, self.act_csv, self.act_xlsx,
                  self.act_recalc):
            a.setEnabled(has_proj)
        for a in (self.act_save, self.act_json):
            a.setEnabled(has_case)
        for w in (self.btn_pick, self.btn_hand, self.btn_annotate, self.btn_done, self.btn_flag):
            w.setEnabled(has_case)
        self.btn_auto_segment.setEnabled(has_case and self._gray is not None)
        has_boxes = has_case and self._gray is not None and any(t.roi is not None for t in self.ann.teeth)
        self.btn_auto_annotate.setEnabled(has_boxes)
        self.btn_auto_annotate.setToolTip(
            "在当前牙框上识别 CEJ、AC、根尖候选；不重新分割，不填写 CEJ下2mm" if has_boxes
            else "请先手动画框选牙或点击「自动分割牙齿」，再执行自动标注")
        self.act_undo_box.setEnabled(has_case and can_undo_box(self.ann))
        self.act_snap.setEnabled(has_case)
        self.btn_cancel_auto.setVisible(self._ai_busy)
        self.btn_cancel_auto.setEnabled(self._ai_busy)
        self.splitter.setEnabled(available)
        self.menuBar().setEnabled(available)
        self.mode_combo.setEnabled(available)
        self.formula_combo.setEnabled(available)
        for action in self.actions():
            action.setEnabled(available)

    def show_help(self) -> None:
        QMessageBox.information(self, "用法与快捷键", HELP_TEXT)

    def show_about(self) -> None:
        QMessageBox.about(self, "关于", ABOUT_TEXT)

    def dragEnterEvent(self, e):
        if not self._ai_busy and e.mimeData().hasUrls() and self.project is not None:
            e.acceptProposedAction()

    def dropEvent(self, e):
        if self.project is None or self._ai_busy:
            return
        paths = [Path(u.toLocalFile()) for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self._do_import(paths)

    def _restore_geometry(self) -> None:
        s = QSettings(ORG, APP)
        if (geo := s.value("geometry")) is not None:
            self.restoreGeometry(geo)
        if (st := s.value("splitter")) is not None:
            self.splitter.restoreState(st)
        self.setAcceptDrops(True)

    def closeEvent(self, e) -> None:
        self._ai.stop()
        self.save_current(silent=True)
        s = QSettings(ORG, APP)
        s.setValue("geometry", self.saveGeometry())
        s.setValue("splitter", self.splitter.saveState())
        super().closeEvent(e)


HELP_TEXT = """\
【工作流】
1. 项目 → 新建项目，选一个空文件夹
2. 把全景片直接拖进窗口（或 Ctrl+I 批量导入）
   · 按文件内容 sha1 自动去重
   · 按文件名自然排序：1, 2, 10 而不是 1, 10, 2
3. 项目 → 导入名册，一次性带入全部年龄
4. 点击「自动分割牙齿」只生成牙齿轮廓和牙框。
   有牙框后，可点击「自动标注」识别 CEJ / AC / 根尖候选，或双击牙框手工标四点。
   两个操作均需主动点击；启动不打开上次项目、不运行模型。
   模型点有轮廓时按轮廓约束，贴线不等于解剖位置已准确。
   编辑 → 候选点贴合牙齿轮廓，可校正旧项目中未人工修改的候选。
   也可按 T 手工画框；牙框在项目内保留便于继续编辑，导出只含当前标点。
   重画会替换对应旧框；重叠多框需选择。Ctrl+Z 撤销框选，重开仍有效。
5. 自动候选带「候」标记，直接拖动调整，或 Enter 放大复核。
   模型的图像左/右需要在放大窗口确认近中/远中；牙位号也可修改。
   每侧保留 CEJ / CEJ下2mm / AC / 根尖四个手工点位，两侧共8点。
   两面四点标完或明确跳过后自动进入下一牙；最后一牙停留，点击「完成标定」。
   自动标注不填写 CEJ下2mm；需要③④公式时请自行补标。
   放大窗口按「完成标定」应用修改，「取消」放弃本次修改。
6. Ctrl+Enter 完成本例并自动跳到下一张

【计算】
   ① 直线法：‖AC−CEJ‖ ÷ ‖根尖−CEJ‖
   ② 投影法：分子改取 (AC−CEJ) 在 CEJ→根尖长轴上的投影（默认）
   ③ 直线法、④ 投影法：以人工标出的 CEJ下2mm 替换起点。
   标满四点后四个公式均可计算，工具栏切换后全项目自动重算。

   骨吸收年龄比 = 最重位点比例 ÷ 年龄
   区间 = 该比例落在 2018 分类的 <15% / 15%–33% / >33% 哪一段
   ⚠ 软件只给数值与区间，不下 Stage/Grade 结论 —— 分期分级需结合临床。

【快捷键】
   T              画框选牙 / 抓手 切换       H  抓手工具
   Ctrl+Z         撤销框选（不删除后来标的点）
   Esc            取消正在画的框
   Enter          开始标定
   Ctrl+Enter     完成本例并下一张
   F              标记存疑          Ctrl+B  收起 / 展开左栏
   Ctrl+←/→       上一张 / 下一张
   Ctrl+S         保存              Ctrl+0  适配窗口
   滚轮           缩放              中键拖/抓手左键拖  平移
   触控板双指     水平/垂直平移
   双击牙框       单牙直接放大；重叠牙框选择 A/B/取消

【标定对话框内】
   空格           下一个点 / 下一颗牙
   Backspace      撤销上一个点
   S              跳过当前这一侧
   F              重新框住本牙
   PageUp/Down    上一颗 / 下一颗
"""

ABOUT_TEXT = """\
<b>全景片牙槽骨吸收测量标注软件</b><br><br>
用于牙周炎研究的批量标注与测量。<br><br>
① 直线法：‖AC−CEJ‖ ÷ ‖根尖−CEJ‖<br>
② 投影法：(AC−CEJ)·(根尖−CEJ) / ‖根尖−CEJ‖²<br><br>
<span style="color:gray">
支持全景片与根尖片（小牙片）两种片型。<br>
软件不输出 Stage / Grade 结论 —— 分期分级需结合缺牙数、探诊、<br>
根分叉、病史等临床资料，由医生判断。
</span>
"""
