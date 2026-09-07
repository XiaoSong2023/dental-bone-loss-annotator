"""左栏：病例列表 + 进度统计 + 右键菜单。

按状态分 Tab：待标注 / 已完成 / 已标记。标完一张自动从「待标注」消失、
计数实时变动 —— 你要的「还剩多少张一目了然」。

缩略图用一个 0 延时定时器逐张后台生成，70 张片子不会卡住界面。
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QProgressBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.project import (
    STATUS_DONE,
    STATUS_FLAGGED,
    STATUS_IN_PROGRESS,
    STATUS_PENDING,
    CaseEntry,
    Project,
)
from ..imaging.loader import load_gray, thumbnail
from . import theme as T
from .widgets.imageutil import gray_to_qpixmap

TABS = [
    ("待标注", (STATUS_PENDING, STATUS_IN_PROGRESS)),
    ("已完成", (STATUS_DONE,)),
    ("已标记", (STATUS_FLAGGED,)),
]

THUMB = QSize(96, 54)


class CasePanel(QWidget):
    case_selected = Signal(object)          # CaseEntry
    rename_requested = Signal(object)       # CaseEntry
    delete_requested = Signal(list)         # list[CaseEntry]
    reveal_requested = Signal(object)       # CaseEntry —— 在资源管理器里打开
    regroup_requested = Signal(list)        # list[CaseEntry] —— 归到同一个病人

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project: Project | None = None
        self._thumbs: dict[str, QIcon] = {}
        self._thumb_queue: list[CaseEntry] = []
        self._timer = QTimer(self)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._make_one_thumb)
        self._filter = ""
        self._periapical = False

        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索病例号…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._on_filter)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabBar().setUsesScrollButtons(False)
        self.tabs.tabBar().setElideMode(Qt.TextElideMode.ElideNone)
        self.lists: list[QListWidget] = []
        for name, _ in TABS:
            lw = QListWidget()
            lw.setIconSize(THUMB)
            lw.setUniformItemSizes(False)
            lw.setAlternatingRowColors(True)
            lw.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            lw.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            lw.customContextMenuRequested.connect(
                lambda pos, w=lw: self._on_context_menu(w, pos)
            )
            lw.itemSelectionChanged.connect(
                lambda w=lw: self._on_select(w)
            )
            self.lists.append(lw)
            self.tabs.addTab(lw, name)

        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        self.progress.setFormat("%v / %m")
        self.counts = QLabel()
        self.counts.setStyleSheet(f"color:{T.NIBI}; font-size:9pt;")

        foot = QHBoxLayout()
        foot.addWidget(self.counts, 1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addWidget(self.search)
        lay.addWidget(self.tabs, 1)
        lay.addWidget(self.progress)
        lay.addLayout(foot)

    # ── 数据 ─────────────────────────────────────────────────────
    def set_periapical(self, on: bool) -> None:
        if self._periapical != on:
            self._periapical = on
            self.refresh()

    def set_project(self, project: Project | None) -> None:
        self.project = project
        self._thumbs.clear()
        self.refresh()

    def refresh(self, keep_selection: CaseEntry | None = None) -> None:
        if self.project is None:
            for lw in self.lists:
                lw.clear()
            self.progress.setMaximum(1)
            self.progress.setValue(0)
            self.counts.setText("未打开项目")
            return

        cases = self.project.sorted_cases()
        for idx, (name, statuses) in enumerate(TABS):
            lw = self.lists[idx]
            lw.blockSignals(True)
            lw.clear()
            n = 0
            for c in cases:
                if c.status not in statuses:
                    continue
                hay = f"{c.case_id} {c.display} {c.patient_key}".lower()
                if self._filter and self._filter not in hay:
                    continue
                n += 1
                item = QListWidgetItem(self._item_text(cases, c))
                item.setData(Qt.ItemDataRole.UserRole, c.case_id)
                icon = self._thumbs.get(c.case_id)
                if icon:
                    item.setIcon(icon)
                else:
                    item.setIcon(QIcon(self._placeholder()))
                if c.status == STATUS_FLAGGED:
                    item.setForeground(QColor(T.YAMABUKI))
                elif c.status == STATUS_DONE:
                    item.setForeground(QColor(T.MATSUBA))
                lw.addItem(item)
            lw.blockSignals(False)
            self.tabs.setTabText(idx, f"{name} ({n})")

        cnt = self.project.counts()
        total = max(1, cnt["total"])
        self.progress.setMaximum(total)
        self.progress.setValue(cnt[STATUS_DONE])
        pct = cnt[STATUS_DONE] * 100 // total
        self.counts.setText(
            f"已完成 <b style='color:{T.MATSUBA}'>{cnt[STATUS_DONE]}</b> · "
            f"剩余 <b style='color:{T.SHU}'>{cnt['remaining']}</b> · "
            f"标记 {cnt[STATUS_FLAGGED]} · 共 {cnt['total']} 张　({pct}%)"
        )

        if keep_selection is not None:
            self.select(keep_selection)
        self._queue_thumbs()

    def _item_text(self, cases: list[CaseEntry], c: CaseEntry) -> str:
        idx = cases.index(c) + 1
        extra = f"　{c.annotated_teeth} 牙" if c.annotated_teeth else ""
        if self._periapical:
            # 根尖片：病人 / 片名 —— 一个病人常有十几张，不带病人名根本分不清
            return f"{c.patient_key}  /  {c.display}{extra}"
        return f"{idx}.  {c.display}{extra}"

    def _placeholder(self) -> QPixmap:
        pm = QPixmap(THUMB)
        pm.fill(QColor(T.BORDER_SOFT))
        return pm

    # ── 选择 ─────────────────────────────────────────────────────
    def _on_select(self, lw: QListWidget) -> None:
        if self.project is None or lw is not self.tabs.currentWidget():
            return
        items = lw.selectedItems()
        if not items:
            return
        case_id = items[0].data(Qt.ItemDataRole.UserRole)
        entry = self.project.find(case_id)
        if entry is not None:
            self.case_selected.emit(entry)

    def select(self, entry: CaseEntry) -> None:
        """在对应的 Tab 里选中某个病例（切 Tab 也一并做掉）。"""
        for idx, (_, statuses) in enumerate(TABS):
            if entry.status not in statuses:
                continue
            lw = self.lists[idx]
            for i in range(lw.count()):
                it = lw.item(i)
                if it.data(Qt.ItemDataRole.UserRole) == entry.case_id:
                    self.tabs.setCurrentIndex(idx)
                    lw.blockSignals(True)
                    lw.setCurrentRow(i)
                    lw.blockSignals(False)
                    lw.scrollToItem(it)
                    return

    # ── 右键菜单 ──────────────────────────────────────────────────
    def _selected_entries(self, lw: QListWidget) -> list[CaseEntry]:
        if self.project is None:
            return []
        out = []
        for it in lw.selectedItems():
            e = self.project.find(it.data(Qt.ItemDataRole.UserRole))
            if e is not None:
                out.append(e)
        return out

    def _on_context_menu(self, lw: QListWidget, pos: QPoint) -> None:
        if self.project is None:
            return
        item = lw.itemAt(pos)
        if item is not None and not item.isSelected():
            lw.setCurrentItem(item)
        entries = self._selected_entries(lw)
        if not entries:
            return

        menu = QMenu(self)
        one = entries[0] if len(entries) == 1 else None

        if one is not None:
            act_open = menu.addAction("打开")
            act_open.triggered.connect(lambda: self.case_selected.emit(one))
            act_rename = menu.addAction("重命名…")
            act_rename.triggered.connect(lambda: self.rename_requested.emit(one))
            menu.addSeparator()

        if self._periapical and len(entries) > 1:
            act_group = menu.addAction(f"归为同一个病人（{len(entries)} 张）…")
            act_group.triggered.connect(lambda: self.regroup_requested.emit(entries))
            menu.addSeparator()

        n = len(entries)
        act_del = menu.addAction("从项目移除…" if n == 1 else f"从项目移除这 {n} 张…")
        act_del.triggered.connect(lambda: self.delete_requested.emit(entries))

        if one is not None:
            menu.addSeparator()
            act_reveal = menu.addAction("在资源管理器中显示")
            act_reveal.triggered.connect(lambda: self.reveal_requested.emit(one))

        menu.exec(lw.viewport().mapToGlobal(pos))

    def _on_filter(self, text: str) -> None:
        self._filter = text.strip().lower()
        self.refresh()

    # ── 缩略图 ────────────────────────────────────────────────────
    def _queue_thumbs(self) -> None:
        if self.project is None:
            return
        todo = [c for c in self.project.sorted_cases() if c.case_id not in self._thumbs]
        if not todo:
            self._timer.stop()
            return
        self._thumb_queue = todo
        self._timer.start()

    def _make_one_thumb(self) -> None:
        if not self._thumb_queue or self.project is None:
            self._timer.stop()
            return
        entry = self._thumb_queue.pop(0)
        try:
            gray = load_gray(self.project.image_path(entry))
        except OSError:
            gray = None
        if gray is not None:
            pm = gray_to_qpixmap(thumbnail(gray, 160)).scaled(
                THUMB, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._thumbs[entry.case_id] = QIcon(pm)
        else:
            self._thumbs[entry.case_id] = QIcon(self._placeholder())

        for lw in self.lists:
            for i in range(lw.count()):
                it = lw.item(i)
                if it.data(Qt.ItemDataRole.UserRole) == entry.case_id:
                    it.setIcon(self._thumbs[entry.case_id])
        if not self._thumb_queue:
            self._timer.stop()
