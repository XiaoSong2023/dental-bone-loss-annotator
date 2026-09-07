"""Protocol fixtures verify operation isolation, not dental model accuracy."""
import copy
import pytest

from app.core.ai_merge import merge_ai_result
from app.core.models import CaseAnnotation, Pt
from tests.test_ai_core import protocol_fixture


def snapshot_result(ann):
    result = protocol_fixture()
    result['mode'] = 'keypoints'
    template = result['teeth'][0]
    result['teeth'] = []
    for tooth in ann.teeth:
        if tooth.roi is None:
            continue
        x, y, w, h = tooth.roi
        result['teeth'].append(dict(
            source_tooth_id=tooth.tooth_id, instance_id=tooth.tooth_id,
            fdi=tooth.fdi, origin=tooth.origin, score=tooth.segmentation.get('score'),
            bbox_xyxy=[x, y, x+w, y+h], contours=copy.deepcopy(tooth.segmentation.get('contours', [])),
            surfaces=copy.deepcopy(template['surfaces'])))
    return result


def test_keypoints_preserve_exact_ids_geometry_and_manual_marks_with_overlapping_boxes():
    ann = CaseAnnotation(image_width=200, image_height=200)
    first = ann.add_tooth(16, (10., 20., 70., 140.))
    second = ann.add_tooth(15, (10., 20., 70., 140.))
    first.segmentation = {'score': .9, 'mask_ref': 'runs/old/masks/first.png', 'contours': [[[10.,20.],[80.,20.],[80.,160.]]]}
    first.initial_auto_roi = (11., 21., 68., 138.)
    first.site('mesial').set('cej', Pt(12.3, 44.5))
    before_geometry = [(t.tooth_id, t.roi, copy.deepcopy(t.segmentation), t.initial_auto_roi) for t in ann.teeth]
    result = snapshot_result(ann)
    result['teeth'].reverse()  # Order or IoU cannot override explicit identity.
    result['teeth'][0]['surfaces'] = []
    summary = merge_ai_result(ann, result)
    assert summary['added_teeth'] == 0 and summary['matched_teeth'] == 2
    assert before_geometry == [(t.tooth_id, t.roi, t.segmentation, t.initial_auto_roi) for t in ann.teeth]
    assert ann.teeth[0].site('mesial').cej.as_tuple() == (12.3, 44.5)
    assert ann.teeth[1].filled_count == 0
    assert ann.teeth[0].site('distal').cej is not None


@pytest.mark.parametrize('mutation', ['unknown_id', 'missing_tooth', 'box', 'contour', 'fdi', 'origin', 'score'])
def test_invalid_keypoints_transaction_cannot_change_selected_teeth(mutation):
    ann = CaseAnnotation(image_width=200, image_height=200)
    ann.add_tooth(16, (10., 20., 70., 140.))
    result = snapshot_result(ann)
    pred = result['teeth'][0]
    if mutation == 'unknown_id':
        pred['source_tooth_id'] = pred['instance_id'] = 'different-tooth'
    elif mutation == 'missing_tooth':
        result['teeth'] = []
    elif mutation == 'box':
        pred['bbox_xyxy'][0] += 1
    elif mutation == 'contour':
        pred['contours'] = [[[10.,20.],[80.,20.],[80.,160.]]]
    elif mutation == 'fdi':
        pred['fdi'] = 15
    elif mutation == 'origin':
        pred['origin'] = 'model'
    elif mutation == 'score':
        pred['score'] = .9
    before = ann.to_dict()
    with pytest.raises(ValueError):
        merge_ai_result(ann, result)
    assert ann.to_dict() == before


def test_manual_box_keypoints_do_not_invent_segmentation_or_initial_auto_roi():
    ann = CaseAnnotation(image_width=200, image_height=200)
    ann.add_tooth(None, (10., 20., 70., 140.))
    result = snapshot_result(ann)
    assert result['teeth'][0]['score'] is None
    merge_ai_result(ann, result)
    assert ann.teeth[0].filled_count == 6
    assert ann.teeth[0].initial_auto_roi is None and ann.teeth[0].segmentation == {}
    assert ann.teeth[0].fdi is None and ann.teeth[0].origin == 'manual'


def test_segmentation_cannot_inject_points_or_modify_existing_marks():
    ann = CaseAnnotation(image_width=200, image_height=200)
    tooth = ann.add_tooth(16, (10., 20., 70., 140.))
    tooth.site('mesial').set('cej', Pt(12.3, 44.5))
    result = protocol_fixture()
    result['mode'] = 'segmentation'
    before = ann.to_dict()
    with pytest.raises(ValueError):
        merge_ai_result(ann, result)
    assert ann.to_dict() == before
    for pred in result['teeth']:
        pred['surfaces'] = []
    merge_ai_result(ann, result)
    assert ann.teeth[0].site('mesial').cej.as_tuple() == (12.3, 44.5)
    assert sum(t.filled_count for t in ann.teeth) == 1


def test_inverse_transform_edge_rounding_is_preserved_as_raw_only():
    ann = CaseAnnotation(image_width=200, image_height=200)
    ann.add_tooth(16, (0., 0., 80., 160.))
    result = snapshot_result(ann)
    point = result['teeth'][0]['surfaces'][0]['points']['cej']
    point['xy'], point['raw_xy'] = [0., 50.], [-1e-6, 50.]
    merge_ai_result(ann, result)
    site = ann.teeth[0].site('mesial')
    assert site.cej.as_tuple() == (0., 50.)
    assert site.point_meta['cej']['raw_xy'] == [-1e-6, 50.]
    invalid = snapshot_result(ann)
    invalid['run_id'] = 'invalid-edge'
    invalid['teeth'][0]['surfaces'][0]['points']['cej']['raw_xy'] = [-.01, 50.]
    before = ann.to_dict()
    with pytest.raises(ValueError):
        merge_ai_result(ann, invalid)
    assert ann.to_dict() == before
