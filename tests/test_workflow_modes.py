"""Unified window contracts with explicitly synthetic protocol fixtures."""
import hashlib
import json
import os
from copy import deepcopy

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
import pytest
from PySide6.QtCore import QRectF, QSettings
from PySide6.QtWidgets import QApplication

from app.core.models import Pt
from app.core.project import Project
from app.imaging.loader import imwrite_unicode
from app.ui import main_window
from app.ui.panorama_view import MODE_HAND


@pytest.fixture
def unified_window(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(main_window.MainWindow, "_restore_geometry", lambda self: None)
    monkeypatch.setattr(main_window, "QSettings", lambda *_:
        QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    project = Project.create(tmp_path / "project")
    source = tmp_path / "protocol-fixture.png"
    imwrite_unicode(source, np.zeros((100, 150), dtype=np.uint8))
    project.import_paths([source])
    window = main_window.MainWindow()
    qtbot.addWidget(window)
    window._test_errors = []
    monkeypatch.setattr(main_window.QMessageBox, "warning", lambda *args: window._test_errors.append(args[-1]))
    window._load_project(project)
    return window


def start_fixture(window, monkeypatch, mode):
    calls = []
    monkeypatch.setattr(window._ai, "start", lambda inp, out, **kw: calls.append((inp, out, kw)))
    (window.start_auto_segmentation if mode == "segmentation" else window.start_auto_annotation)()
    inp, out, opts = calls[-1]
    out.mkdir()
    result = {"status": "completed", "run_id": "explicit-ui-fixture", "mode": mode,
              "image": {"width": 150, "height": 100,
                        "sha256": hashlib.sha256(inp.read_bytes()).hexdigest(),
                        "coordinate_space": "canonical_image_pixel_centers"}, "teeth": []}
    if mode == "keypoints":
        snapshot = json.loads(opts["teeth_path"].read_text(encoding="utf-8"))
        result["teeth"] = [deepcopy(tooth) | {"surfaces": []} for tooth in snapshot["teeth"]]
        result["teeth_source"] = {"sha256": hashlib.sha256(opts["teeth_path"].read_bytes()).hexdigest()}
    return opts, out / "result.json", result


def apply_fixture(window, path, result):
    path.write_text(json.dumps(result), encoding="utf-8")
    window._ai_completed(str(path))


@pytest.mark.parametrize("legacy_mode", [None, "manual", "full"])
def test_launch_is_same_blank_hand_ui_and_never_reopens_last_project(qtbot, tmp_path, monkeypatch, legacy_mode):
    previous = Project.create(tmp_path / "last-project")
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue("last_project", str(previous.root))
    monkeypatch.setattr(main_window, "QSettings", lambda *_: settings)
    calls = []
    monkeypatch.setattr(main_window.AiClient, "start", lambda *args, **kw: calls.append((args, kw)))
    window = main_window.MainWindow(annotation_mode=legacy_mode)
    qtbot.addWidget(window)
    QApplication.processEvents()
    qtbot.wait(10)
    assert window.project is window.entry is window.ann is None
    assert window._gray is None and not window.view.has_image and not calls
    assert window.view.mode == MODE_HAND and window.btn_hand.isChecked()
    assert window.windowTitle() == main_window.APP_TITLE
    assert window.btn_auto_segment.text() == "自动分割牙齿"
    assert window.btn_auto_annotate.text() == "自动标注"
    assert not window.btn_auto_segment.isEnabled() and not window.btn_auto_annotate.isEnabled()
    assert window.formula_combo.count() == 4


def test_annotation_requires_existing_box_and_loading_does_not_run_models(unified_window, monkeypatch):
    window = unified_window
    monkeypatch.setattr(window._ai, "start", lambda *args, **kwargs: pytest.fail("no box: must not start"))
    assert window.btn_auto_segment.isEnabled() and not window.btn_auto_annotate.isEnabled()
    window.start_auto_annotation()
    assert not window._ai_busy and "先手动画框" in window.hint_label.text()
    window.ann.add_tooth(16, (10, 10, 40, 80))
    window._update_enabled()
    assert window.btn_auto_annotate.isEnabled()


def test_segmentation_only_requests_boxes_and_rejects_pose_operation(unified_window, monkeypatch):
    window = unified_window
    opts, path, result = start_fixture(window, monkeypatch, "segmentation")
    assert opts == {"mode": "segmentation"}
    assert window.act_snap.isVisible()
    result["mode"] = "keypoints"
    apply_fixture(window, path, result)
    assert window._test_errors and not window.ann.ai_runs and not window._ai_busy


def test_removing_last_box_disables_auto_annotation(unified_window, monkeypatch):
    window = unified_window
    tooth = window.ann.add_tooth(16, (10, 10, 40, 80))
    window._refresh_all()
    assert window.btn_auto_annotate.isEnabled()
    monkeypatch.setattr(main_window.QMessageBox, "question",
                        lambda *args: main_window.QMessageBox.StandardButton.Yes)
    window._remove_tooth(tooth.index)
    assert window.ann.teeth == [] and not window.btn_auto_annotate.isEnabled()


def test_segmentation_preserves_four_points_and_does_not_project_old_candidates(unified_window, monkeypatch):
    window = unified_window
    tooth = window.ann.add_tooth(16, (10, 10, 40, 80))
    for role, point in zip(("cej", "cej2", "ac", "apex"), [(15, 20), (16, 25), (17, 35), (18, 75)]):
        tooth.site("mesial").set(role, Pt(*point))
    original = tooth.site("mesial").to_dict(0)
    monkeypatch.setattr(main_window, "constrain_pending_candidates", lambda *_: pytest.fail("segmentation must not move points"))
    _opts, path, result = start_fixture(window, monkeypatch, "segmentation")
    result["teeth"] = [{"instance_id": "fixture", "fdi": 16, "score": .9,
                        "bbox_xyxy": [10, 10, 50, 90], "surfaces": [],
                        "contours": [[[10, 10], [50, 10], [50, 90]]]}]
    apply_fixture(window, path, result)
    assert not window._test_errors and len(window.ann.teeth) == 1
    assert window.ann.teeth[0].site("mesial").to_dict(0) == original
    assert window.ann.ai_runs[-1]["mode"] == "segmentation"


def test_keypoints_uses_exact_manual_box_snapshot_and_never_resegments(unified_window, monkeypatch):
    window = unified_window
    tooth = window.ann.add_tooth(16, (10, 10, 40, 80))
    identity, box, segmentation = tooth.tooth_id, tooth.roi, deepcopy(tooth.segmentation)
    opts, path, result = start_fixture(window, monkeypatch, "keypoints")
    assert opts["mode"] == "keypoints"
    snapshot = json.loads(opts["teeth_path"].read_text(encoding="utf-8"))
    assert snapshot["teeth"] == [{"source_tooth_id": identity, "instance_id": identity,
        "fdi": 16, "origin": "manual", "score": None, "bbox_xyxy": [10, 10, 50, 90], "contours": []}]
    assert snapshot["image"]["sha256"] == result["image"]["sha256"]
    result["teeth"][0]["surfaces"] = [{"object_score": .9, "points": {
        "cej": {"xy": [20, 20], "score": .9}, "bone_level": {"xy": [20, 35], "score": .8},
        "apex": {"xy": [20, 75], "score": .7}}}]
    apply_fixture(window, path, result)
    assert not window._test_errors and len(window.ann.teeth) == 1
    saved = window.ann.teeth[0]
    assert (saved.tooth_id, saved.roi, saved.segmentation) == (identity, box, segmentation)
    assert saved.site("mesial").filled_count == 3 and saved.site("mesial").cej2 is None
    assert saved.site("mesial").point_meta["cej"]["boundary_projection"] is None
    assert window.ann.ai_runs[-1]["analysis_input"]["teeth_ref"].endswith("/teeth.json")


@pytest.mark.parametrize("change", ["unknown_id", "missing_tooth", "changed_result_box", "changed_current_box", "changed_snapshot", "wrong_snapshot_hash"])
def test_keypoints_rejects_result_not_bound_to_frozen_teeth(unified_window, monkeypatch, change):
    window = unified_window
    tooth = window.ann.add_tooth(16, (10, 10, 40, 80))
    opts, path, result = start_fixture(window, monkeypatch, "keypoints")
    if change == "unknown_id":
        result["teeth"][0]["source_tooth_id"] = "not-in-this-run"
    elif change == "missing_tooth":
        result["teeth"] = []
    elif change == "changed_result_box":
        result["teeth"][0]["bbox_xyxy"][0] = 11
    elif change == "changed_current_box":
        tooth.roi = (11, 10, 39, 80)
    elif change == "wrong_snapshot_hash":
        result["teeth_source"]["sha256"] = "0" * 64
    else:
        data = json.loads(opts["teeth_path"].read_text(encoding="utf-8"))
        data["teeth"][0]["bbox_xyxy"][0] = 11
        opts["teeth_path"].write_text(json.dumps(data), encoding="utf-8")
    before = window.ann.to_dict()
    apply_fixture(window, path, result)
    assert window._test_errors and window.ann.to_dict() == before
    assert not window._ai_busy


def test_redraw_replaces_existing_box_without_fdi_prompt_and_undo_restores(unified_window, monkeypatch):
    window = unified_window
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


def test_direct_tooth_activation_opens_selected_tooth_without_confirmation(unified_window, monkeypatch):
    window = unified_window
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
