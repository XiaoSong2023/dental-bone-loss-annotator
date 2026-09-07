"""Manual four-point progression; geometry fixtures are not model predictions."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
import pytest
from PySide6.QtCore import QPointF

from app.core.formula import FormulaConfig, get
from app.core.models import CaseAnnotation, Pt, ROLES, SURFACES
from app.ui.tooth_dialog import STEPS, ToothDialog


@pytest.fixture
def dialog(qtbot):
    ann = CaseAnnotation(image_width=600, image_height=400)
    ann.add_tooth(16, (40, 40, 100, 300))
    ann.add_tooth(15, (220, 40, 100, 300))
    dlg = ToothDialog(np.zeros((400, 600), dtype=np.uint8), ann, ann.teeth[:],
                      get(ann.formula_id), FormulaConfig())
    qtbot.addWidget(dlg)
    return dlg


def fill_tooth(tooth):
    for sf in SURFACES:
        for index, role in enumerate(ROLES):
            tooth.site(sf).set(role, Pt(70 if sf == "mesial" else 100, 70 + index * 50))


def test_eight_manual_points_advance_only_after_both_surfaces_complete(dialog):
    first = dialog.tooth
    for i in range(7):
        dialog._on_click(QPointF(70 + (i // 4) * 30, 70 + (i % 4) * 50))
        assert dialog._ti == 0
    dialog._on_click(QPointF(100, 220))
    assert dialog._ti == 1 and first.filled_count == 8
    assert first.site("mesial").cej2 is not None
    assert first.site("distal").cej2 is not None
    assert len(first.sites) == 2


def test_skipping_both_surfaces_advances_once(dialog):
    first = dialog.tooth
    dialog._toggle_skip("mesial", True)
    assert dialog._ti == 0 and dialog.step[0] == "distal"
    dialog._toggle_skip("distal", True)
    assert dialog._ti == 1 and all(site.skipped for site in first.sites)


def test_completion_search_returns_to_earlier_hole_instead_of_skipping_tooth(dialog):
    first = dialog.tooth
    fill_tooth(first)
    first.site("mesial").set("cej2", None)
    first.site("distal").set("apex", None)
    dialog._si = STEPS.index(("distal", "apex"))
    dialog._on_click(QPointF(100, 220))
    assert dialog._ti == 0 and dialog.step == ("mesial", "cej2")
    dialog._on_click(QPointF(70, 120))
    assert dialog._ti == 1


def test_dragging_or_opening_complete_tooth_never_auto_advances(dialog):
    fill_tooth(dialog.tooth)
    dialog._goto_tooth(0)
    assert dialog._ti == 0
    dialog._on_drag(dialog.tooth, dialog.tooth.site("mesial"), "cej", QPointF(72, 71))
    assert dialog._ti == 0
    before = dialog.tooth.to_dict()
    dialog._on_click(QPointF(85, 200))
    assert dialog._ti == 0 and dialog.tooth.to_dict() == before


def test_final_tooth_stays_for_explicit_completion_and_cancel_remains_transactional(dialog):
    dialog._goto_tooth(1)
    for i in range(8):
        dialog._on_click(QPointF(250 + (i // 4) * 30, 70 + (i % 4) * 50))
    assert dialog._ti == 1 and dialog._tooth_complete()
    assert "完成标定" in dialog.hint.text() and dialog.btn_done.isEnabled()
    assert dialog._original_ann.teeth[1].filled_count == 0
    dialog.reject()
    assert dialog._original_ann.teeth[1].filled_count == 0


def test_undo_after_automatic_advance_returns_to_previous_tooth(dialog):
    for i in range(8):
        dialog._on_click(QPointF(70 + (i // 4) * 30, 70 + (i % 4) * 50))
    assert dialog._ti == 1
    dialog.undo()
    assert dialog._ti == 0 and dialog.step == ("distal", "apex")
    assert dialog.tooth.site("distal").apex is None
    assert dialog.tooth.filled_count == 7
