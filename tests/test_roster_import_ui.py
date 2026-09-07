"""Real roster parsing and UI persistence with synthetic metadata/image fixtures.

No segmentation or landmark model is invoked by these regression tests.
"""
import csv
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtCore import QSettings

from app.core.models import Pt
from app.core.project import Project
from app.imaging.loader import imwrite_unicode
from app.ui import main_window


@pytest.mark.parametrize("extension", [".xlsx", ".csv"])
@pytest.mark.parametrize("selected_index", [0, 1, 2])
def test_roster_keeps_current_case_metadata_and_unsaved_points(
    qtbot, tmp_path, monkeypatch, extension, selected_index
):
    monkeypatch.setattr(main_window.MainWindow, "_restore_geometry", lambda self: None)
    monkeypatch.setattr(main_window, "QSettings", lambda *_:
        QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    messages = []
    monkeypatch.setattr(main_window.QMessageBox, "information",
                        lambda _parent, _title, text: messages.append(text))
    project = Project.create(tmp_path / "project")
    window = main_window.MainWindow()
    qtbot.addWidget(window)
    window._load_project(project)
    sources = []
    for i, name in enumerate(("001_测试甲", "002_测试乙", "003_测试丙")):
        source = tmp_path / f"{name}.png"
        pixels = (np.arange(8000).reshape(80, 100) + i).astype(np.uint8)
        imwrite_unicode(source, pixels)
        sources.append(source)
    window._do_import(sources)
    current = project.cases[selected_index]
    window.open_case(current)
    assert window.ann.patient.age is None and window.ann.patient.sex == ""
    window.inspector.note.setText("未保存的人工备注")
    window.inspector.note.editingFinished.emit()
    tooth = window.ann.add_tooth(16, (10, 10, 50, 60))
    tooth.site("mesial").cej = Pt(20.5, 30.25)
    window._mark_dirty()

    roster_path = tmp_path / f"社区名册{extension}"
    data = [["病例号", "年龄", "性别"],
            ["001_测试甲", 61, "女"], ["002_测试乙", 52, "男"], ["003_测试丙", 43, "女"]]
    if extension == ".xlsx":
        from openpyxl import Workbook
        workbook = Workbook()
        for row in data:
            workbook.active.append(row)
        workbook.save(roster_path)
        workbook.close()
    else:
        with roster_path.open("w", encoding="utf-8-sig", newline="") as stream:
            csv.writer(stream).writerows(data)
    monkeypatch.setattr(main_window.QFileDialog, "getOpenFileName",
                        lambda *_args: (str(roster_path), ""))

    window.import_roster()
    assert window.entry is current
    assert window.inspector.age.value() == data[selected_index + 1][1]
    assert window.inspector.sex.currentText() == data[selected_index + 1][2]
    assert window.ann.patient.note == "未保存的人工备注"
    assert "实际写入 3 例" in messages[-1]
    # A second import, edit/save, navigation and reopen must not erase the import.
    window.import_roster()
    assert "实际写入 0 例" in messages[-1]
    window.inspector.note.setText("导入后继续人工备注")
    window.inspector.note.editingFinished.emit()
    window.save_current(silent=True)
    window.open_case(project.cases[(selected_index + 1) % 3])
    window.open_case(current)
    assert window.inspector.age.value() == data[selected_index + 1][1]
    assert window.inspector.sex.currentText() == data[selected_index + 1][2]
    reopened = Project.open(project.root)
    for entry, expected in zip(reopened.cases, data[1:]):
        ann = reopened.load_annotation(entry)
        assert (ann.patient.id, ann.patient.age, ann.patient.sex) == tuple(expected)
        if entry.case_id == current.case_id:
            assert ann.patient.note == "导入后继续人工备注"
            assert ann.teeth[0].site("mesial").cej.as_tuple() == (20.5, 30.25)
