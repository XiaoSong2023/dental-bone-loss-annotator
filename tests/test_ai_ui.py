"""UI/protocol tests use explicit fixtures; they do not validate model accuracy."""
import os
import sys
import hashlib
import json
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from app.core.formula import FormulaConfig, get
from app.core.models import CaseAnnotation, Pt
from app.ui.panorama_view import PanoramaView
from app.ui.tooth_dialog import ToothDialog
from app.ui.widgets.point_item import PointItem


def test_drag_point_stays_in_image(qtbot):
    view = PanoramaView()
    qtbot.addWidget(view)
    ann = CaseAnnotation(image_width=100, image_height=80)
    tooth = ann.add_tooth(16, (5, 5, 80, 70))
    tooth.site("mesial").cej = Pt(20, 20)
    view.set_case(np.zeros((80, 100), dtype=np.uint8), ann)
    item = next(i for i in view.scene_().items() if isinstance(i, PointItem))
    item.setPos(QPointF(-50, 500))
    assert item.pos() == QPointF(0, 79)


def test_cancel_dialog_does_not_change_annotation(qtbot):
    ann = CaseAnnotation(image_width=100, image_height=80)
    tooth = ann.add_tooth(16, (5, 5, 80, 70))
    tooth.site("mesial").cej = Pt(20, 20)
    before = ann.to_dict()
    dlg = ToothDialog(np.zeros((80, 100), dtype=np.uint8), ann, ann.teeth[:],
                      get(ann.formula_id), FormulaConfig())
    qtbot.addWidget(dlg)
    dlg.tooth.site("mesial").set("cej", Pt(40, 35))
    dlg.reject()
    assert ann.to_dict() == before


def test_accept_dialog_applies_edits(qtbot):
    ann = CaseAnnotation(image_width=100, image_height=80)
    tooth = ann.add_tooth(16, (5, 5, 80, 70))
    dlg = ToothDialog(np.zeros((80, 100), dtype=np.uint8), ann, ann.teeth[:],
                      get(ann.formula_id), FormulaConfig())
    qtbot.addWidget(dlg)
    dlg.tooth.site("mesial").set("cej", Pt(40, 35))
    dlg.accept()
    assert ann.teeth[0].site("mesial").cej.as_tuple() == (40, 35)


def test_worker_protocol_requires_successful_complete_file(qtbot, tmp_path):
    from app.ui.ai_client import AiClient
    script = tmp_path / "protocol_fixture.py"
    script.write_text(
        "import argparse,json,pathlib\n"
        "p=argparse.ArgumentParser()\n"
        "[p.add_argument(x) for x in ('--input','--models','--output')]\n"
        "a=p.parse_args(); out=pathlib.Path(a.output); out.mkdir()\n"
        "print(json.dumps({'type':'progress','stage':'protocol_fixture','current':1,'total':1}),flush=True)\n"
        "result=out/'result.json'; result.write_text('{}')\n"
        "print(json.dumps({'type':'result','result_path':str(result)}),flush=True)\n",
        encoding="utf-8",
    )
    client = AiClient()
    events = []
    client.progress.connect(events.append)
    with qtbot.waitSignal(client.completed, timeout=5000) as result:
        client.start(tmp_path / "unused_fixture.png", tmp_path / "output",
                     command=[sys.executable, str(script)], models=tmp_path, cwd=tmp_path)
    assert Path(result.args[0]).is_file()
    assert events[0]["stage"] == "protocol_fixture"
    assert not client.busy


def test_worker_cancel_never_applies_partial_result(qtbot, tmp_path):
    from app.ui.ai_client import AiClient
    script = tmp_path / "cancel_fixture.py"
    script.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
    client = AiClient()
    results = []
    client.completed.connect(results.append)
    client.start(tmp_path / "unused_fixture.png", tmp_path / "output",
                 command=[sys.executable, str(script)], models=tmp_path, cwd=tmp_path)
    qtbot.waitUntil(lambda: client.process.processId() != 0, timeout=5000)
    with qtbot.waitSignal(client.cancelled, timeout=5000):
        client.cancel()
    assert not client.busy and not results


def test_busy_ui_binds_case_and_uses_unadjusted_pixels(qtbot, tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings
    from app.core.project import Project
    from app.imaging.loader import imwrite_unicode, load_gray
    from app.ui import main_window
    monkeypatch.setattr(main_window.MainWindow, "_restore_geometry", lambda self: None)
    monkeypatch.setattr(main_window, "QSettings", lambda *args:
                        QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    project = Project.create(tmp_path / "project")
    image = np.arange(8000, dtype=np.uint8).reshape(80, 100)
    source = tmp_path / "fixture.png"
    imwrite_unicode(source, image)
    entries, _ = project.import_paths([source])
    window = main_window.MainWindow()
    qtbot.addWidget(window)
    window._load_project(project)
    original_case = window.entry
    called = []
    monkeypatch.setattr(window._ai, "start", lambda input_path, output, **kwargs:
                        called.append((input_path, output)))
    window._adjust.invert = True
    window.start_auto_segmentation()
    assert window._ai_busy
    assert not window.btn_auto_segment.isEnabled() and not window.cases.isEnabled()
    assert window.btn_cancel_auto.isEnabled()
    assert np.array_equal(load_gray(called[0][0]), image)
    window.open_case(object())
    assert window.entry is original_case
    window._ai_cancelled()
    assert not window._ai_busy and window.btn_auto_segment.isEnabled()
    assert not window.btn_auto_annotate.isEnabled()
    assert window.ann.teeth == []


def test_candidate_review_keeps_raw_and_requires_explicit_side(qtbot):
    ann = CaseAnnotation(image_width=100, image_height=80)
    tooth = ann.add_tooth(16, (5, 5, 80, 70))
    tooth.origin = "model"
    tooth.segmentation = {"contours": [[[10, 10], [80, 10], [70, 70], [20, 70]]]}
    site = tooth.site("mesial")
    site.cej = Pt(20, 20)
    site.image_side = "image_left"
    site.side_confirmed = False
    site.point_meta["cej"] = {
        "origin": "model", "raw_xy": [20, 20], "edited": False,
        "review_status": "pending", "history": [], "model_id": "explicit-ui-fixture",
    }
    dlg = ToothDialog(np.zeros((80, 100), dtype=np.uint8), ann, ann.teeth[:],
                      get(ann.formula_id), FormulaConfig())
    qtbot.addWidget(dlg)
    editable = dlg.tooth.site("mesial")
    assert "待确认" in dlg.site_heads["mesial"].text()
    dlg._on_drag(dlg.tooth, editable, "cej", QPointF(30, 25))
    assert editable.point_meta["cej"]["raw_xy"] == [20, 20]
    assert editable.point_meta["cej"]["edited"]
    assert not editable.side_confirmed
    assert editable.cej2 is None
    dlg._confirm_side("mesial", dlg.side_boxes["mesial"].findData("distal"))
    assert dlg.tooth.site("distal") is editable
    assert editable.side_confirmed and editable.surface == "distal"
    assert ann.teeth[0].site("mesial").cej.as_tuple() == (20, 20)
    dlg.accept()
    restored = CaseAnnotation.from_dict(ann.to_dict())
    assert restored.teeth[0].site("distal").cej.as_tuple() == (30, 25)
    assert restored.teeth[0].site("distal").point_meta["cej"]["raw_xy"] == [20, 20]


@pytest.fixture
def ai_completion_window(qtbot, tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QMessageBox
    from app.core.project import Project
    from app.imaging.loader import imwrite_unicode
    from app.ui import main_window
    monkeypatch.setattr(main_window.MainWindow, "_restore_geometry", lambda self: None)
    monkeypatch.setattr(main_window, "QSettings", lambda *_args:
                        QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    errors = []
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _title, text: errors.append(text))
    source = tmp_path / "explicit-ui-protocol-fixture.png"
    imwrite_unicode(source, np.zeros((80, 100), dtype=np.uint8))
    project = Project.create(tmp_path / "project")
    project.import_paths([source])
    window = main_window.MainWindow()
    qtbot.addWidget(window)
    window._load_project(project)
    paths = []
    monkeypatch.setattr(window._ai, "start", lambda input_path, output, **kwargs: paths.append((input_path, output)))

    def prepare(status="done", teeth=True):
        project.set_status(window.entry, status)
        window.start_auto_segmentation()
        input_path, output = paths[-1]
        output.mkdir()
        result = {"run_id": "explicit-ui-protocol-fixture", "status": "completed", "mode": "segmentation",
                  "image": {"width": 100, "height": 80,
                            "sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
                            "coordinate_space": "canonical_image_pixel_centers"},
                  "teeth": [{"instance_id": "fixture-tooth", "fdi": 16, "score": .9,
                             "bbox_xyxy": [5, 5, 80, 70], "contours": [], "surfaces": []}] if teeth else []}
        return output / "result.json", result

    return window, errors, prepare


@pytest.mark.parametrize("invalid_field,invalid_value", [
    ("sha256", "0" * 64), ("coordinate_space", "normalized_coordinates"),
])
def test_same_size_wrong_image_or_coordinate_space_is_rejected(ai_completion_window, invalid_field, invalid_value):
    window, errors, prepare = ai_completion_window
    path, result = prepare()
    before = window.ann.to_dict()
    result["image"][invalid_field] = invalid_value
    path.write_text(json.dumps(result), encoding="utf-8")
    window._ai_completed(str(path))
    assert errors and window.ann.to_dict() == before
    assert window.entry.status == "done" and not window._ai_busy


@pytest.mark.parametrize("previous_status,has_predictions,expected_status", [
    ("done", True, "in_progress"), ("flagged", True, "flagged"),
    ("pending", True, "in_progress"), ("done", False, "done"),
])
def test_new_candidates_reset_done_but_preserve_flagged(ai_completion_window, previous_status, has_predictions, expected_status):
    window, errors, prepare = ai_completion_window
    path, result = prepare(previous_status, has_predictions)
    path.write_text(json.dumps(result), encoding="utf-8")
    window._ai_completed(str(path))
    assert not errors
    assert window.entry.status == window.ann.status == expected_status
    assert window.project.load_annotation(window.entry).status == expected_status
    run = window.ann.ai_runs[-1]
    assert run["source_case"]["sha1"] == window.entry.sha1
    assert run["analysis_input"]["sha256"] == result["image"]["sha256"]
    assert run["analysis_input"]["preconversion"] == "opencv_grayscale_uint8"
    assert run["analysis_input"]["display_adjust_used"] is False
