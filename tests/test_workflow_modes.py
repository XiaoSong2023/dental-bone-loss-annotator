"""Window-level contracts with explicitly synthetic protocol fixtures."""
import hashlib
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
import pytest
from PySide6.QtCore import QRectF, QSettings

from app.core.models import Pt
from app.core.project import Project
from app.imaging.loader import imwrite_unicode
from app.ui import main_window


@pytest.fixture
def manual_window(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(main_window.MainWindow, "_restore_geometry", lambda self: None)
    monkeypatch.setattr(main_window, "QSettings", lambda *_:
        QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    project = Project.create(tmp_path / "project")
    source = tmp_path / "protocol-fixture.png"
    imwrite_unicode(source, np.zeros((100, 150), dtype=np.uint8))
    project.import_paths([source])
    window = main_window.MainWindow(annotation_mode="manual")
    qtbot.addWidget(window)
    window._load_project(project)
    return window


def test_manual_mode_only_requests_segmentation_and_rejects_pose_results(manual_window, monkeypatch):
    window = manual_window
    calls, errors = [], []
    monkeypatch.setattr(window._ai, "start", lambda inp, out, **kw: calls.append((inp, out, kw)))
    monkeypatch.setattr(main_window.QMessageBox, "warning", lambda *args: errors.append(args[-1]))
    assert not window.act_snap.isVisible()
    assert window.btn_auto.text() == "自动分割牙齿"
    window.start_auto_annotation()
    inp, out, opts = calls[-1]
    assert opts == {"mode": "segmentation"}
    out.mkdir()
    result = {"status": "completed", "run_id": "fixture", "mode": "full",
              "image": {"width": 150, "height": 100,
                        "sha256": hashlib.sha256(inp.read_bytes()).hexdigest(),
                        "coordinate_space": "canonical_image_pixel_centers"}, "teeth": []}
    path = out / "result.json"
    path.write_text(json.dumps(result), encoding="utf-8")
    window._ai_completed(str(path))
    assert errors and not window.ann.ai_runs and not window._ai_busy


def test_manual_mode_merges_boxes_without_touching_four_points(manual_window, monkeypatch):
    window = manual_window
    tooth = window.ann.add_tooth(16, (10, 10, 40, 80))
    for role, point in zip(("cej", "cej2", "ac", "apex"), [(15, 20), (16, 25), (17, 35), (18, 75)]):
        tooth.site("mesial").set(role, Pt(*point))
    original = tooth.site("mesial").to_dict(0)
    calls = []
    monkeypatch.setattr(window._ai, "start", lambda inp, out, **kw: calls.append((inp, out)))
    window.start_auto_annotation()
    inp, out = calls[-1]
    out.mkdir()
    result = {"status": "completed", "run_id": "segmentation-fixture", "mode": "segmentation",
              "image": {"width": 150, "height": 100,
                        "sha256": hashlib.sha256(inp.read_bytes()).hexdigest(),
                        "coordinate_space": "canonical_image_pixel_centers"},
              "teeth": [{"instance_id": "fixture", "fdi": 16, "score": .9,
                        "bbox_xyxy": [10, 10, 50, 90], "surfaces": [],
                        "contours": [[[10, 10], [50, 10], [50, 90]]]}]}
    path = out / "result.json"
    path.write_text(json.dumps(result), encoding="utf-8")
    window._ai_completed(str(path))
    assert len(window.ann.teeth) == 1
    assert window.ann.teeth[0].site("mesial").to_dict(0) == original
    assert window.ann.ai_runs[-1]["mode"] == "segmentation"


def test_redraw_replaces_existing_box_without_fdi_prompt_and_undo_restores(manual_window, monkeypatch):
    window = manual_window
    tooth = window.ann.add_tooth(16, (10, 10, 40, 80))
    tooth.site("mesial").set("cej", Pt(20, 20))
    monkeypatch.setattr(main_window.QInputDialog, "getInt", lambda *args: pytest.fail("replacement must not ask FDI"))
    window._on_box_drawn(QRectF(8, 8, 44, 84))
    assert len(window.ann.teeth) == 1 and tooth.roi == (8, 8, 44, 84)
    assert window.act_undo_box.isEnabled()
    window.undo_box_edit()
    assert tooth.roi == (10, 10, 40, 80)
    assert tooth.site("mesial").cej.as_tuple() == (20., 20.)
    reopened = window.project.load_annotation(window.entry)
    assert reopened.teeth[0].roi == tooth.roi and reopened.box_history[-1]["undone"]


def test_direct_tooth_activation_opens_selected_tooth_without_confirmation(manual_window, monkeypatch):
    window = manual_window
    window.ann.add_tooth(16, (10, 10, 40, 80))
    target = window.ann.add_tooth(15, (70, 10, 40, 80))
    selected = []
    class ProbeDialog:
        def __init__(self, gray, ann, teeth, formula, config, parent):
            self.teeth = teeth
        def _goto_tooth(self, index):
            selected.append(self.teeth[index].tooth_id)
        def exec(self):
            return 0
    monkeypatch.setattr(main_window, "ToothDialog", ProbeDialog)
    window.view.tooth_activated.emit(target)
    assert selected == [target.tooth_id]
