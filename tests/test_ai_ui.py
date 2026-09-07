"""UI/protocol tests use explicit fixtures; they do not validate model accuracy."""
import os
import sys
from pathlib import Path

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
    monkeypatch.setattr(window._ai, "start", lambda input_path, output:
                        called.append((input_path, output)))
    window._adjust.invert = True
    window.start_auto_annotation()
    assert window._ai_busy
    assert not window.btn_auto.isEnabled() and not window.cases.isEnabled()
    assert window.btn_cancel_auto.isEnabled()
    assert np.array_equal(load_gray(called[0][0]), image)
    window.open_case(object())
    assert window.entry is original_case
    window._ai_cancelled()
    assert not window._ai_busy and window.btn_auto.isEnabled()
    assert window.ann.teeth == []
