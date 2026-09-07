"""Merge model candidates without overwriting manual marks or inventing missing points."""
from __future__ import annotations

import copy
import math
from pathlib import PurePosixPath

from .models import CaseAnnotation, Pt


def _xy(value, width, height):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("自动点坐标格式错误")
    x, y = map(float, value)
    if not math.isfinite(x) or not math.isfinite(y) or not (0 <= x < width and 0 <= y < height):
        raise ValueError("自动点超出原图或包含无效数值")
    return [x, y]


def _score(value):
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise ValueError("模型 score 无效")
    return number


def _iou(roi, box):
    if roi is None:
        return 0.
    x, y, w, h = roi
    a, b, c, d = box
    overlap = max(0., min(x+w, c)-max(x, a)) * max(0., min(y+h, d)-max(y, b))
    return overlap / max(w*h + (c-a)*(d-b)-overlap, 1e-12)


def _match_score(tooth, prediction):
    score = _iou(tooth.roi, prediction["bbox_xyxy"])
    previous_box = tooth.segmentation.get("bbox_xyxy")
    if previous_box and len(previous_box) == 4:
        a, b, c, d = previous_box
        score = max(score, _iou((a, b, c-a, d-b), prediction["bbox_xyxy"]))
    if score >= .5 or tooth.roi is None:
        return score
    # A hand-drawn context box may deliberately be larger than the tooth mask.
    # Only use this fallback with the same known FDI and mutually centered boxes.
    if tooth.fdi is None or tooth.fdi != prediction.get("fdi") or score < .15:
        return score
    x, y, w, h = tooth.roi
    a, b, c, d = prediction["bbox_xyxy"]
    overlap = max(0., min(x+w, c)-max(x, a)) * max(0., min(y+h, d)-max(y, b))
    contained = overlap / ((c-a)*(d-b)) >= .9
    centered = a <= x+w/2 <= c and b <= y+h/2 <= d
    return .5 if contained and centered else score


def _relative(value):
    path = PurePosixPath(str(value).replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or ":" in str(path):
        raise ValueError("模型产物引用必须在项目内")
    return path


def merge_ai_result(ann: CaseAnnotation, result: dict) -> dict:
    """Apply one complete run transactionally; anatomical sides remain unconfirmed.

Legacy mesial/distal slots hold image-left/image-right candidate groups until the
reviewer explicitly confirms them. Existing manually marked groups are preserved.
"""
    counts = {"added_teeth": 0, "matched_teeth": 0, "points_added": 0, "teeth_without_points": 0}
    if result.get("status") != "completed":
        raise ValueError("只能应用已完整结束的自动结果")
    run_id = result.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("自动结果缺少 run_id")
    if any(run.get("run_id") == run_id for run in ann.ai_runs):
        return counts
    width, height = ann.image_width, ann.image_height
    image = result.get("image", {})
    if (image.get("width"), image.get("height")) != (width, height) or min(width, height) <= 0:
        raise ValueError("自动结果图像尺寸与当前病例不一致")
    result_ref = result.get("result_ref")
    relative_root = _relative(result_ref).parent if result_ref else None
    predictions = copy.deepcopy(result.get("teeth", []))
    seen = set()
    for prediction in predictions:
        ident = prediction.get("instance_id")
        if not isinstance(ident, str) or not ident or ident in seen:
            raise ValueError("自动牙实例 ID 缺失或重复")
        seen.add(ident)
        a, b, c, d = map(float, prediction["bbox_xyxy"])
        if not all(math.isfinite(v) for v in (a, b, c, d)) or not (0 <= a < c <= width and 0 <= b < d <= height):
            raise ValueError("自动牙框超出原图或无效")
        prediction["bbox_xyxy"] = [a, b, c, d]
        _score(prediction["score"])
        for contour in prediction.get("contours", []):
            for xy in contour:
                _xy(xy, width, height)
        for surface in prediction.get("surfaces", []):
            _score(surface["object_score"])
            for kind in ("cej", "bone_level", "apex"):
                point = surface.get("points", {}).get(kind)
                if point is not None:
                    point["xy"] = _xy(point["xy"], width, height)
                    if point.get("raw_xy") is not None:
                        point["raw_xy"] = _xy(point["raw_xy"], width, height)
                    _score(point["score"])
        if prediction.get("mask_ref"):
            _relative(prediction["mask_ref"])

    working = copy.deepcopy(ann)
    matched_ids = set()
    for prediction in predictions:
        box = prediction["bbox_xyxy"]
        a, b, c, d = box
        possible = [tooth for tooth in working.teeth if tooth.tooth_id not in matched_ids]
        tooth = max(possible, key=lambda t: _match_score(t, prediction), default=None)
        if tooth is None or _match_score(tooth, prediction) < .5:
            tooth = working.add_tooth(prediction.get("fdi"), (a, b, c-a, d-b))
            tooth.origin = "model"
            counts["added_teeth"] += 1
        else:
            counts["matched_teeth"] += 1
            if tooth.fdi is None:
                tooth.fdi = prediction.get("fdi")
        matched_ids.add(tooth.tooth_id)
        if tooth.initial_auto_roi is None:
            tooth.initial_auto_roi = (a, b, c-a, d-b)
        mask_ref = prediction.get("mask_ref")
        if mask_ref and relative_root is not None:
            mask_ref = str(relative_root / _relative(mask_ref))
        tooth.segmentation = {"run_id": run_id, "instance_id": prediction["instance_id"],
                              "score": prediction["score"], "bbox_xyxy": box,
                              "contours": prediction.get("contours", []), "mask_ref": mask_ref}
        tooth.segmentation["contour_sha256"] = prediction.get("contour_sha256")
        surfaces = prediction.get("surfaces", [])
        tooth.candidate_surfaces.extend(copy.deepcopy([s | {"run_id": run_id} for s in surfaces]))
        if not surfaces:
            counts["teeth_without_points"] += 1
        selected = {}
        for candidate in surfaces:
            cej = candidate.get("points", {}).get("cej")
            if cej is None:
                continue
            image_side = "image_left" if cej["xy"][0] < (a+c)/2 else "image_right"
            if image_side not in selected or candidate["object_score"] > selected[image_side]["object_score"]:
                selected[image_side] = candidate
        for image_side, candidate in selected.items():
            slot = "mesial" if image_side == "image_left" else "distal"
            site = tooth.site(slot)
            # Already labelled anatomical/manual groups must not acquire a new guessed meaning.
            if site.skipped or (site.filled_count and site.image_side != image_side):
                continue
            if site.filled_count == 0:
                site.image_side, site.side_confirmed = image_side, False
            for kind, role in (("cej", "cej"), ("bone_level", "ac"), ("apex", "apex")):
                point = candidate.get("points", {}).get(kind)
                if (point is None or site.get(role) is not None
                        or site.point_meta.get(role, {}).get("review_status") == "rejected"):
                    continue
                site.set(role, Pt(*point["xy"]))
                site.point_meta[role] = {"origin": "model", "raw_xy": list(point.get("raw_xy", point["xy"])),
                                         "projected_xy": copy.deepcopy(point.get("projected_xy")),
                                         "boundary_projection": copy.deepcopy(point.get("boundary_projection")),
                                         "score": point["score"], "run_id": run_id,
                                         "model_id": "denpar-surface-pose", "edited": False,
                                         "review_status": "pending", "history": []}
                counts["points_added"] += 1
    working.ai_runs.append({"run_id": run_id, "result_ref": result_ref, "counts": counts.copy(),
                            "image": copy.deepcopy(image), "models": copy.deepcopy(result.get("models", {})),
                            "source_case": copy.deepcopy(result.get("source_case", {})),
                            "analysis_input": copy.deepcopy(result.get("analysis_input", {})),
                            "created_at_utc": result.get("created_at_utc"),
                            "elapsed_seconds": result.get("elapsed_seconds"),
                            "preprocessing": copy.deepcopy(result.get("preprocessing", {})),
                            "domain_validation": result.get("domain_validation"),
                            "accuracy": result.get("accuracy"),
                            "mode": result.get("mode", "full"),
                            "training_steps": result.get("training_steps"), "device": result.get("device", "cpu"),
                            "status": result.get("status"), "merge_policy": "preserve_existing_marks_fill_empty_groups"})
    working.status = "in_progress"
    working.touch()
    ann.teeth, ann.ai_runs = working.teeth, working.ai_runs
    ann.status, ann.created, ann.updated = working.status, working.created, working.updated
    return counts
