"""Qt gesture tests with explicit geometry fixtures, not dental predictions."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QMenu
from PySide6.QtTest import QTest

from app.core.models import CaseAnnotation, Pt
from app.ui.panorama_view import MODE_HAND, MODE_PICK, PanoramaView


def settle():
    QApplication.processEvents()


def drag(view, start, end, button=Qt.MouseButton.MiddleButton):
    QTest.mousePress(view.viewport(), button, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(view.viewport(), (start + end) / 2)
    settle()
    QTest.mouseMove(view.viewport(), end)
    settle()
    QTest.mouseRelease(view.viewport(), button, Qt.KeyboardModifier.NoModifier, end)
    settle()


def canvas(qtbot, teeth=0):
    view = PanoramaView()
    qtbot.addWidget(view)
    view.resize(700, 500)
    ann = CaseAnnotation(image_width=600, image_height=400)
    for i in range(teeth):
        ann.add_tooth(16+i, (100+i*15, 70, 230, 260))
    view.set_case(np.zeros((400, 600), dtype=np.uint8), ann)
    view.show()
    settle()
    view.fit()
    return view, ann


def test_middle_drag_pans_even_when_whole_image_fits(qtbot):
    view, _ann = canvas(qtbot)
    scale = view.current_scale()
    point = QPointF(300, 200)
    before = view.mapFromScene(point)
    start = view.viewport().rect().center()
    drag(view, start, start + QPoint(70, 40))
    after = view.mapFromScene(point)
    assert abs(after.x() - before.x() - 70) <= 1
    assert abs(after.y() - before.y() - 40) <= 1
    assert view.current_scale() == scale
    assert view.scene_().sceneRect().width() == 600


def test_trackpad_pixel_delta_pans_without_zoom(qtbot):
    view, _ann = canvas(qtbot)
    center = view.viewport().rect().center()
    point = QPointF(300, 200)
    before = view.mapFromScene(point)
    scale = view.current_scale()
    wheel = QWheelEvent(QPointF(center), QPointF(view.viewport().mapToGlobal(center)),
                        QPoint(52, 17), QPoint(), Qt.MouseButton.NoButton,
                        Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.ScrollUpdate, False)
    QApplication.sendEvent(view.viewport(), wheel)
    settle()
    after = view.mapFromScene(point)
    assert abs(after.x() - before.x() - 52) <= 1
    assert abs(after.y() - before.y() - 17) <= 1
    assert view.current_scale() == scale


def test_vertical_wheel_still_zooms(qtbot):
    view, _ann = canvas(qtbot)
    center = view.viewport().rect().center()
    scale = view.current_scale()
    wheel = QWheelEvent(QPointF(center), QPointF(view.viewport().mapToGlobal(center)),
                        QPoint(), QPoint(0, 120), Qt.MouseButton.NoButton,
                        Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(view.viewport(), wheel)
    assert abs(view.current_scale() / scale - 1.18) < 1e-9


def test_hand_tool_pans_blank_but_keeps_point_dragging(qtbot):
    view, ann = canvas(qtbot, teeth=1)
    site = ann.teeth[0].site("mesial")
    site.cej = Pt(200, 200)
    view.refresh_overlay()
    view.point_dragged.connect(lambda _t, s, r, p: s.set(r, Pt(p.x(), p.y())))
    view.set_mode(MODE_HAND)
    blank = view.mapFromScene(QPointF(500, 200))
    anchor = QPointF(50, 50)
    before = view.mapFromScene(anchor)
    drag(view, blank, blank + QPoint(30, 18), Qt.MouseButton.LeftButton)
    assert (view.mapFromScene(anchor) - before).manhattanLength() >= 45
    before_point = site.cej.as_tuple()
    before_anchor = view.mapFromScene(anchor)
    start = view.mapFromScene(QPointF(*before_point))
    drag(view, start, start + QPoint(20, 15), Qt.MouseButton.LeftButton)
    assert site.cej.as_tuple() != before_point
    assert view.mapFromScene(anchor) == before_anchor
    assert view.cursor().shape() == Qt.CursorShape.OpenHandCursor


def test_review_canvas_hand_and_middle_drag_do_not_place_points(qtbot):
    from app.ui.tooth_dialog import AnnotateCanvas
    view = AnnotateCanvas()
    qtbot.addWidget(view)
    view.resize(700, 500)
    ann = CaseAnnotation(image_width=600, image_height=400)
    view.set_case(np.zeros((400, 600), dtype=np.uint8), ann)
    view.show()
    settle()
    clicks = []
    view.canvas_clicked.connect(clicks.append)
    view.set_hand_tool(True)
    center = view.viewport().rect().center()
    anchor = QPointF(100, 100)
    before = view.mapFromScene(anchor)
    drag(view, center, center + QPoint(40, 30), Qt.MouseButton.LeftButton)
    drag(view, center, center + QPoint(-20, -15), Qt.MouseButton.MiddleButton)
    assert not clicks and ann.teeth == []
    assert view.mapFromScene(anchor) != before


def test_dragged_view_destruction_leaves_next_event_loop_safe(qtbot):
    # Exercise real Qt destruction, then another event loop. PointItem signal
    # closures must not retain a view whose scene has already been destroyed.
    view = PanoramaView()
    view.resize(700, 500)
    ann = CaseAnnotation(image_width=600, image_height=400)
    site = ann.add_tooth(16, (100, 70, 230, 260)).site("mesial")
    site.cej = Pt(200, 200)
    view.set_case(np.zeros((400, 600), dtype=np.uint8), ann)
    view.point_dragged.connect(lambda _t, s, r, p: s.set(r, Pt(p.x(), p.y())))
    view.show()
    settle()
    view.set_mode(MODE_HAND)
    start = view.mapFromScene(QPointF(200, 200))
    drag(view, start, start + QPoint(20, 15), Qt.MouseButton.LeftButton)
    assert site.cej.as_tuple() != (200, 200)
    view.close()
    deleted = []
    view.destroyed.connect(lambda: deleted.append(True))
    view.deleteLater()
    qtbot.waitUntil(lambda: bool(deleted), timeout=1000)
    qtbot.wait(20)


def test_double_click_single_tooth_activates_directly(qtbot):
    view, ann = canvas(qtbot, teeth=1)
    view.set_mode(MODE_HAND)
    selected = []
    view.tooth_activated.connect(selected.append)
    position = view.mapFromScene(QPointF(200, 200))
    QTest.mouseDClick(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, position)
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, position)
    settle()
    assert selected == [ann.teeth[0]]


def choose_popup_action(index, captured):
    menu = QApplication.activePopupWidget()
    if not isinstance(menu, QMenu):
        captured["error"] = f"Expected QMenu, got {type(menu).__name__}"
        return
    actions = [action for action in menu.actions() if not action.isSeparator()]
    captured["labels"] = [action.text() for action in actions]
    target = actions[index]
    QTest.mouseClick(menu, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     menu.actionGeometry(target).center())


def test_overlapping_boxes_list_every_hit_and_select_third(qtbot):
    view, ann = canvas(qtbot, teeth=3)
    selected, captured = [], {}
    view.tooth_activated.connect(selected.append)
    QTest.mouseDClick(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     view.mapFromScene(QPointF(200, 200)))
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                       view.mapFromScene(QPointF(200, 200)))
    qtbot.waitUntil(lambda: isinstance(QApplication.activePopupWidget(), QMenu))
    choose_popup_action(2, captured)
    settle()
    assert len(captured["labels"]) == 4
    assert [name.split(" · ")[0] for name in captured["labels"][:3]] == ["方框 A", "方框 B", "方框 C"]
    assert captured["labels"][-1] == "取消"
    assert selected == [ann.teeth[2]]


def test_overlap_cancel_keeps_annotations_and_emits_nothing(qtbot):
    view, ann = canvas(qtbot, teeth=3)
    selected, captured = [], {}
    before = ann.to_dict()
    view.tooth_activated.connect(selected.append)
    QTest.mouseDClick(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     view.mapFromScene(QPointF(200, 200)))
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                       view.mapFromScene(QPointF(200, 200)))
    qtbot.waitUntil(lambda: isinstance(QApplication.activePopupWidget(), QMenu))
    choose_popup_action(-1, captured)
    settle()
    assert selected == [] and ann.to_dict() == before


def test_explicit_box_mode_only_emits_roi_and_space_pan_does_not_draw(qtbot):
    view, ann = canvas(qtbot, teeth=1)
    before = ann.to_dict()
    boxes = []
    view.box_drawn.connect(boxes.append)
    view.set_mode(MODE_PICK)
    start = view.mapFromScene(QPointF(110, 100))
    end = view.mapFromScene(QPointF(330, 300))
    QTest.keyPress(view, Qt.Key.Key_Space)
    drag(view, start, end, Qt.MouseButton.LeftButton)
    QTest.keyRelease(view, Qt.Key.Key_Space)
    assert boxes == []
    assert view.cursor().shape() == Qt.CursorShape.CrossCursor
    view.fit()
    start = view.mapFromScene(QPointF(110, 100))
    end = view.mapFromScene(QPointF(330, 300))
    drag(view, start, end, Qt.MouseButton.LeftButton)
    assert len(boxes) == 1 and boxes[0].width() > 210 and boxes[0].height() > 190
    assert ann.to_dict() == before


def test_small_pan_steps_do_not_accumulate_rounding_drift(qtbot):
    view, _ann = canvas(qtbot)
    view.resize(701, 501)
    settle()
    view.fit()
    point = QPointF(300, 200)
    before = view.mapFromScene(point)
    for _ in range(80):
        view.pan_by_pixels(QPointF(1, 1))
    after = view.mapFromScene(point)
    assert abs(after.x() - before.x() - 80) <= 1
    assert abs(after.y() - before.y() - 80) <= 1


def test_boundary_candidate_tooltip_keeps_score_and_explains_projection(qtbot):
    from app.ui.widgets.point_item import PointItem
    view, ann = canvas(qtbot, teeth=1)
    site = ann.teeth[0].site("mesial")
    site.cej = Pt(200, 200)
    site.point_meta["cej"] = {
        "origin": "model", "raw_xy": [195.7, 200], "projected_xy": [200, 200],
        "boundary_projection": {"distance_px": 4.3}, "score": .61,
        "review_status": "pending", "edited": False, "history": [],
    }
    view.refresh_overlay()
    item = next(item for item in view.scene_().items() if isinstance(item, PointItem))
    assert "轮廓约束候选，移动 4.3 px；仍需解剖复核" in item.toolTip()
    assert site.point_meta["cej"]["score"] == .61
