"""Geometric review operations. Projection is not anatomical landmark detection."""
from __future__ import annotations

import math
import hashlib
import json
from datetime import datetime, timezone

from .models import CaseAnnotation, Pt, Tooth


def project_to_contours(xy, contours):
    """Exact closest point on the closed polygons displayed by the viewer."""
    x, y = map(float, xy)
    best = None
    for ci, contour in enumerate(contours):
        if len(contour) < 3:
            continue
        for si, (a, b) in enumerate(zip(contour, contour[1:] + contour[:1])):
            ax, ay = map(float, a)
            bx, by = map(float, b)
            dx, dy = bx-ax, by-ay
            length2 = dx*dx + dy*dy
            t = max(0., min(1., ((x-ax)*dx + (y-ay)*dy) / length2)) if length2 else 0.
            px, py = ax+t*dx, ay+t*dy
            distance = math.hypot(x-px, y-py)
            if best is None or distance < best[1]["distance_px"]:
                best = ([px, py], {"method": "nearest_closed_contour_segment",
                        "contour_index": ci, "segment_index": si, "segment_t": t,
                        "distance_px": distance, "reference": "displayed_segmentation_contours"})
    return best


def constrain_pending_candidates(ann: CaseAnnotation) -> dict:
    """Only move unedited, unreviewed model points. Missing points stay missing."""
    counts = {"projected": 0, "missing_contour": 0, "max_distance_px": 0.}
    for tooth in ann.teeth:
        contours = tooth.segmentation.get("contours", [])
        contour_hash = hashlib.sha256(json.dumps(contours, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        for site in tooth.sites:
            for role in ("cej", "ac", "apex"):
                point, meta = site.get(role), site.point_meta.get(role, {})
                if (point is None or meta.get("origin") != "model" or meta.get("edited")
                        or meta.get("review_status") in ("reviewed", "rejected")):
                    continue
                raw = meta.get("raw_xy") or list(point.as_tuple())
                projection = project_to_contours(raw, contours)
                if projection is None:
                    counts["missing_contour"] += 1
                    continue
                xy, correction = projection
                correction["run_id"] = tooth.segmentation.get("run_id")
                correction["contour_sha256"] = contour_hash
                setattr(site, role, Pt(*xy))  # Geometry must not count as human review.
                meta["raw_xy"], meta["projected_xy"] = list(raw), xy
                meta["boundary_projection"] = correction
                meta["review_status"] = "pending"
                counts["projected"] += 1
                counts["max_distance_px"] = max(counts["max_distance_px"], correction["distance_px"])
    return counts


def replacement_candidates(ann: CaseAnnotation, roi) -> list[Tooth]:
    """Offer intersecting, centrally related rectangles; never choose an ambiguous tooth."""
    x, y, w, h = roi
    matches = []
    for tooth in ann.teeth:
        if tooth.roi is None:
            continue
        a, b, c, d = tooth.roi
        intersection = max(0., min(x+w, a+c)-max(x, a)) * max(0., min(y+h, b+d)-max(y, b))
        if intersection <= 0:
            continue
        centers = (a <= x+w/2 <= a+c and b <= y+h/2 <= b+d) or (x <= a+c/2 <= x+w and y <= b+d/2 <= y+h)
        if centers or intersection / min(w*h, c*d) >= .5:
            matches.append((intersection / (w*h+c*d-intersection), tooth))
    return [tooth for _, tooth in sorted(matches, key=lambda item: item[0], reverse=True)]


def edit_box(ann: CaseAnnotation, roi, tooth: Tooth | None = None, *, fdi=None) -> Tooth:
    x, y, w, h = map(float, roi)
    if not all(math.isfinite(v) for v in (x, y, w, h)) or not (
            0 <= x < x+w <= ann.image_width and 0 <= y < y+h <= ann.image_height):
        raise ValueError("牙框必须位于原图内，且宽高大于零")
    created = tooth is None
    if tooth is not None and tooth not in ann.teeth:
        raise ValueError("要替换的牙齿不在当前病例中")
    if created:
        tooth = ann.add_tooth(fdi)
    previous = list(tooth.roi) if tooth.roi else None
    if previous == [x, y, w, h]:
        return tooth
    ann.box_history.append({"tooth_id": tooth.tooth_id, "previous_roi": previous,
        "current_roi": [x, y, w, h], "created_tooth": created,
        "at": datetime.now(timezone.utc).isoformat(), "undone": False})
    tooth.roi = (x, y, w, h)
    return tooth


def can_undo_box(ann: CaseAnnotation) -> bool:
    ids = {t.tooth_id for t in ann.teeth}
    return any(not e.get("undone") and e["tooth_id"] in ids for e in ann.box_history)


def undo_box(ann: CaseAnnotation) -> bool:
    teeth = {t.tooth_id: t for t in ann.teeth}
    for edit in reversed(ann.box_history):
        if edit.get("undone") or edit["tooth_id"] not in teeth:
            continue
        tooth = teeth[edit["tooth_id"]]
        tooth.roi = tuple(edit["previous_roi"]) if edit["previous_roi"] else None
        # Never delete landmarks acquired after the rectangle was created.
        if edit.get("created_tooth") and not tooth.filled_count and not tooth.segmentation:
            ann.remove_tooth(tooth)
        edit["undone"] = True
        edit["undone_at"] = datetime.now(timezone.utc).isoformat()
        return True
    return False
