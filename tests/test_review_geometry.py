"""Engineering geometry/persistence fixtures; no model accuracy assertions."""
import pytest

from app.core.models import CaseAnnotation, Pt
from app.core.review_geometry import (project_to_contours, constrain_pending_candidates,
    edit_box, undo_box, can_undo_box, replacement_candidates)
from app.core.storage import load_annotation, save_annotation


def test_exact_segment_projection_not_nearest_vertex():
    xy, meta = project_to_contours((4.25, 2.), [[[0, 0], [10, 0], [10, 10], [0, 10]]])
    assert xy == [4.25, 0.]
    assert meta["distance_px"] == 2.
    assert meta["segment_t"] == .425


def test_projection_handles_closing_edge_and_degenerate_segments():
    assert project_to_contours((-2., 7.), [[[0, 0], [0, 0], [10, 0], [0, 10]]])[0] == [0., 7.]
    assert project_to_contours((0, 0), []) is None


def test_projection_preserves_raw_and_manual_edits_and_missing_points(tmp_path):
    ann = CaseAnnotation(image_width=100, image_height=100)
    tooth = ann.add_tooth(16, (10, 10, 40, 70))
    tooth.segmentation = {"contours": [[[10, 10], [50, 10], [50, 80], [10, 80]]]}
    site = tooth.site("mesial")
    site.cej, site.apex = Pt(12.25, 25), Pt(30, 75)
    site.point_meta = {"cej": {"origin": "model", "raw_xy": [12.25, 25], "edited": False},
                       "apex": {"origin": "model", "raw_xy": [29, 70], "edited": True}}
    assert constrain_pending_candidates(ann)["projected"] == 1
    assert site.cej.as_tuple() == (10., 25.)
    assert site.apex.as_tuple() == (30., 75.)
    assert site.ac is None and site.cej2 is None
    assert site.point_meta["cej"]["raw_xy"] == [12.25, 25]
    assert site.point_meta["cej"]["review_status"] == "pending"
    save_annotation(tmp_path / "case.json", ann)
    assert load_annotation(tmp_path / "case.json").teeth[0].site("mesial").point_meta == site.point_meta


def test_redraw_undo_survives_save_and_keeps_points_and_initial_box(tmp_path):
    ann = CaseAnnotation(image_width=100, image_height=100)
    tooth = ann.add_tooth(16, (10, 10, 20, 50))
    tooth.initial_auto_roi = tooth.roi
    tooth.site("mesial").set("cej", Pt(12, 20))
    assert replacement_candidates(ann, (8, 8, 25, 55)) == [tooth]
    edit_box(ann, (8, 8, 25, 55), tooth)
    edit_box(ann, (7, 7, 27, 57), tooth)
    assert len(ann.teeth) == 1
    save_annotation(tmp_path / "case.json", ann)
    restored = load_annotation(tmp_path / "case.json")
    assert can_undo_box(restored) and undo_box(restored) and undo_box(restored)
    assert restored.teeth[0].roi == restored.teeth[0].initial_auto_roi == (10, 10, 20, 50)
    assert restored.teeth[0].site("mesial").cej.as_tuple() == (12., 20.)
    assert not can_undo_box(restored)


def test_undo_new_box_does_not_delete_later_manual_points():
    ann = CaseAnnotation(image_width=100, image_height=100)
    tooth = edit_box(ann, (10, 10, 30, 60), fdi=16)
    tooth.site("mesial").set("cej", Pt(20, 20))
    assert undo_box(ann)
    assert ann.teeth == [tooth] and tooth.roi is None
    assert tooth.filled_count == 1
    with pytest.raises(ValueError):
        edit_box(ann, (-1, 0, 10, 10))


def test_ambiguous_box_returns_all_candidates():
    ann = CaseAnnotation(image_width=100, image_height=100)
    a = ann.add_tooth(16, (10, 10, 30, 60))
    b = ann.add_tooth(15, (30, 10, 30, 60))
    assert set(t.tooth_id for t in replacement_candidates(ann, (15, 10, 40, 60))) == {a.tooth_id, b.tooth_id}


def test_rerun_keeps_identity_after_large_manual_reframe():
    from app.core.ai_merge import merge_ai_result
    ann = CaseAnnotation(image_width=200, image_height=100)
    result = {"status": "completed", "run_id": "fixture-run-1", "image": {"width": 200, "height": 100},
              "teeth": [{"instance_id": "fixture", "fdi": 16, "score": .9,
                         "bbox_xyxy": [10, 10, 50, 90], "contours": [], "surfaces": []}]}
    merge_ai_result(ann, result)
    tooth = ann.teeth[0]
    edit_box(ann, (1, 1, 150, 98), tooth)
    result["run_id"] = "fixture-run-2"
    merge_ai_result(ann, result)
    assert len(ann.teeth) == 1 and ann.teeth[0].tooth_id == tooth.tooth_id
    assert ann.teeth[0].roi == (1, 1, 150, 98)
    assert undo_box(ann) and ann.teeth[0].roi == (10, 10, 40, 80)
