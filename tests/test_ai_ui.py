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
