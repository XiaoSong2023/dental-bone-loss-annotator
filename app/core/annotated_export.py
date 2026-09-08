"""Offline annotated image package; only saved, current image-pixel coordinates.

PNG is a static preview. HTML embeds the same grayscale image and an SVG overlay;
its own zoom control keeps point glyphs at a constant screen size. No Qt or network.
"""

from __future__ import annotations

import base64
import hashlib
from html import escape
import json
import math
from pathlib import Path
import re
import tempfile
from typing import Callable, Iterable
from urllib.parse import quote
from zipfile import ZIP_DEFLATED, ZipFile

import cv2
import numpy as np

from ..imaging.loader import ImageAdjust, apply_adjust, load_gray
from . import geometry
from .formula import FORMULAS
from .models import CaseAnnotation, ROLES, ROLE_SHORT, point_label
from .project import CaseEntry, Project


def _number(value: float) -> str:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("标注中存在非有限坐标，无法导出图片")
    return repr(value)


def _overlay(ann: CaseAnnotation) -> tuple[list[dict], list[dict], list[dict]]:
    """One geometry source for both preview rendering and the interactive viewer."""
    shapes, marks, captions = [], [], []
    formula = FORMULAS.get(ann.formula_id)
    origin_role = "cej2" if formula and "cej2" in formula.needs else "cej"
    for tooth in ann.teeth:
        color = tooth.color
        for contour in tooth.segmentation.get("contours", []):
            if len(contour) >= 3:
                shapes.append(dict(kind="polygon", points=contour, color=color,
                                   width=1.3, opacity=1.0, fill=22 / 255))
        if tooth.roi:
            x, y, w, h = tooth.roi
            shapes.append(dict(kind="polygon", points=[(x, y), (x+w, y),
                                (x+w, y+h), (x, y+h)], color=color, width=1.6,
                                opacity=0.45 if tooth.complete else 0.85,
                                dash="9.6 6.4", fill=0))
        anchor = tooth.roi[:2] if tooth.roi else next(
            (s.cej.as_tuple() for s in tooth.sites if s.cej), None)
        if anchor:
            captions.append(dict(x=anchor[0], y=anchor[1], text=tooth.name, color=color))
        for site in tooth.sites:
            if site.skipped:
                continue
            origin, apex = site.get(origin_role), site.apex
            if origin and apex:
                shapes.append(dict(kind="line", points=[origin.as_tuple(), apex.as_tuple()],
                                   color=color, width=1.1, opacity=0.8, dash="5.5 4.4"))
                if site.ac:
                    foot = geometry.foot_of_perpendicular(
                        site.ac.as_tuple(), origin.as_tuple(), apex.as_tuple())
                    shapes.append(dict(kind="line", points=[site.ac.as_tuple(), foot],
                                       color=color, width=1.0, opacity=0.9, dash="1 2"))
                    shapes.append(dict(kind="line", points=[origin.as_tuple(), foot],
                                       color=color, width=3.0, opacity=0.55))
            for role in ROLES:
                pt = site.get(role)
                if pt is None:
                    continue
                meta = site.point_meta.get(role, {})
                pending = meta.get("origin") == "model" and meta.get("review_status") != "reviewed"
                label = point_label(tooth.index, site.surface, role)
                marks.append(dict(x=pt.x, y=pt.y, role=role, label=label,
                                  pending=pending, color=color,
                                  title=f"{tooth.name} · {site.display_label} · {label} · {ROLE_SHORT[role]}"
                                        + (" · 待复核候选" if pending else "")))
    return shapes, marks, captions


def _svg_overlay(shapes: list[dict], marks: list[dict], captions: list[dict]) -> str:
    parts = []
    for shape in shapes:
        coords = " ".join(",".join(_number(v) for v in p) for p in shape["points"])
        tag = "polygon" if shape["kind"] == "polygon" else "polyline"
        fill = shape["color"] if shape.get("fill") else "none"
        parts.append(f'<{tag} points="{coords}" fill="{fill}" '
                     f'fill-opacity="{shape.get("fill", 0)}" stroke="{shape["color"]}" '
                     f'stroke-width="{shape["width"]}" opacity="{shape["opacity"]}" '
                     f'stroke-dasharray="{shape.get("dash", "none")}" vector-effect="non-scaling-stroke"/>')
    for mark in marks:
        x, y, color = _number(mark["x"]), _number(mark["y"]), mark["color"]
        label = escape(mark["label"] + ("·候" if mark["pending"] else ""))
        parts.append(f'<g class="mark" data-role="{mark["role"]}" data-x="{x}" data-y="{y}" '
                     f'transform="translate({x} {y})"><title>{escape(mark["title"])}</title>'
                     f'<g class="fixed-size" fill="none" stroke="{color}">'
                     '<path d="M-11 0H11M0-11V11" stroke="#000" stroke-opacity="0.67" stroke-width="3"/>'
                     '<path d="M-11 0H11M0-11V11" stroke-width="1.4"/>'
                     '<circle r="5" stroke="#000" stroke-opacity="0.78" stroke-width="2.4"/>'
                     f'<circle r="5" stroke-width="1.8" fill="{color}" fill-opacity="0.35"/>'
                     f'<text x="14" y="-9" font-size="12" font-weight="700" fill="{color}" '
                     f'stroke="#000" stroke-width="2" paint-order="stroke">{label}</text></g></g>')
    for caption in captions:
        parts.append(f'<g transform="translate({_number(caption["x"])} {_number(caption["y"])})">'
                     '<g class="fixed-size">'
                     f'<text y="-4" font-size="12" font-weight="700" fill="{caption["color"]}" '
                     f'stroke="#12161c" stroke-width="4" paint-order="stroke">{escape(caption["text"])}</text>'
                     '</g></g>')
    return "".join(parts)


def _png_bytes(image: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise OSError("无法编码导出图片")
    return encoded.tobytes()


def _render_png(gray: np.ndarray, shapes: list[dict], marks: list[dict], captions: list[dict]) -> bytes:
    canvas = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    def color(hex_color):
        return tuple(int(hex_color[i:i+2], 16) for i in (5, 3, 1))

    def fixed_point(point):
        return tuple(round(float(v) * 256) for v in point)

    for shape in shapes:
        layer = canvas.copy()
        rgb = color(shape["color"])
        points = shape["points"]
        polygon = np.array([fixed_point(p) for p in points], dtype=np.int32)
        if shape.get("fill"):
            cv2.fillPoly(layer, [polygon], rgb, cv2.LINE_AA, shift=8)
            canvas = cv2.addWeighted(layer, shape["fill"], canvas, 1-shape["fill"], 0)
            layer = canvas.copy()
        edges = list(zip(points, points[1:]))
        if shape["kind"] == "polygon":
            edges.append((points[-1], points[0]))
        for start, end in edges:
            start, end = np.array(start, dtype=float), np.array(end, dtype=float)
            length = float(np.linalg.norm(end-start))
            dash, gap = [float(v) for v in shape["dash"].split()] if shape.get("dash") else (length+1, 0)
            for distance in np.arange(0, max(length, 0.01), dash+gap):
                a = start + (end-start) * distance / max(length, 0.01)
                b = start + (end-start) * min(distance+dash, length) / max(length, 0.01)
                cv2.line(layer, fixed_point(a), fixed_point(b), rgb,
                         max(1, round(shape["width"])), cv2.LINE_AA, shift=8)
        canvas = cv2.addWeighted(layer, shape["opacity"], canvas, 1-shape["opacity"], 0)
    for mark in marks:
        x, y = float(mark["x"]), float(mark["y"])
        center, rgb = fixed_point((x, y)), color(mark["color"])
        for thickness, c in ((3, (0, 0, 0)), (1, rgb)):
            cv2.line(canvas, fixed_point((x-11, y)), fixed_point((x+11, y)), c, thickness, cv2.LINE_AA, shift=8)
            cv2.line(canvas, fixed_point((x, y-11)), fixed_point((x, y+11)), c, thickness, cv2.LINE_AA, shift=8)
        layer = canvas.copy()
        cv2.circle(layer, center, 5*256, rgb, -1, cv2.LINE_AA, shift=8)
        canvas = cv2.addWeighted(layer, 0.35, canvas, 0.65, 0)
        cv2.circle(canvas, center, 5*256, (0, 0, 0), 3, cv2.LINE_AA, shift=8)
        cv2.circle(canvas, center, 5*256, rgb, 1, cv2.LINE_AA, shift=8)
        label = mark["label"] + ("*" if mark["pending"] else "")
        for thickness, c in ((3, (0, 0, 0)), (1, rgb)):
            cv2.putText(canvas, label, (round(x+14), round(y-9)), cv2.FONT_HERSHEY_SIMPLEX,
                        0.4, c, thickness, cv2.LINE_AA)
    for caption in captions:
        for thickness, c in ((3, (18, 22, 28)), (1, color(caption["color"]))):
            cv2.putText(canvas, caption["text"], (round(caption["x"]), round(caption["y"]-4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, c, thickness, cv2.LINE_AA)
    return _png_bytes(canvas)


_VIEWER_SCRIPT = r"""
const svg = document.getElementById('viewer'), scene = document.getElementById('scene');
const glyphs = [...document.querySelectorAll('.fixed-size')];
const width = Number(svg.dataset.imageWidth), height = Number(svg.dataset.imageHeight);
let scale = 1, tx = 0, ty = 0, drag = null;
function render() {
  scene.setAttribute('transform', `translate(${tx} ${ty}) scale(${scale})`);
  for (const glyph of glyphs) glyph.setAttribute('transform', `scale(${1 / scale})`);
  document.getElementById('zoom-value').textContent = `${Math.round(scale * 100)}%`;
}
function zoomAt(factor, x, y) {
  const next = Math.min(100, Math.max(0.005, scale * factor));
  tx = x - (x - tx) * next / scale; ty = y - (y - ty) * next / scale;
  scale = next; render();
}
function fit() {
  scale = Math.max(0.005, Math.min(svg.clientWidth / width, svg.clientHeight / height) * 0.96);
  tx = (svg.clientWidth - width * scale) / 2; ty = (svg.clientHeight - height * scale) / 2; render();
}
document.getElementById('fit').onclick = fit;
document.getElementById('zoom-in').onclick = () => zoomAt(1.4, svg.clientWidth/2, svg.clientHeight/2);
document.getElementById('zoom-out').onclick = () => zoomAt(1/1.4, svg.clientWidth/2, svg.clientHeight/2);
document.getElementById('actual').onclick = () => zoomAt(1/scale, svg.clientWidth/2, svg.clientHeight/2);
svg.addEventListener('wheel', e => {
  e.preventDefault();
  if (e.shiftKey || (!e.ctrlKey && Math.abs(e.deltaX) > Math.abs(e.deltaY))) {
    tx -= e.deltaX || e.deltaY; ty -= e.deltaX ? e.deltaY : 0; render();
  } else {
    const rect = svg.getBoundingClientRect();
    const delta = e.deltaY * (e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? svg.clientHeight : 1);
    zoomAt(Math.exp(-Math.max(-500, Math.min(500, delta))*0.002), e.clientX-rect.left, e.clientY-rect.top);
  }
}, {passive: false});
svg.addEventListener('pointerdown', e => {
  if (e.button !== 0 && e.button !== 1) return;
  e.preventDefault(); svg.setPointerCapture(e.pointerId);
  drag = {id: e.pointerId, x: e.clientX, y: e.clientY}; svg.classList.add('dragging');
});
svg.addEventListener('pointermove', e => {
  if (!drag || drag.id !== e.pointerId) return;
  tx += e.clientX-drag.x; ty += e.clientY-drag.y;
  drag.x=e.clientX; drag.y=e.clientY; render();
});
function endDrag() { drag=null; svg.classList.remove('dragging'); }
svg.addEventListener('pointerup', endDrag); svg.addEventListener('pointercancel', endDrag);
svg.addEventListener('lostpointercapture', endDrag);
svg.addEventListener('dblclick', fit);
window.addEventListener('resize', fit);
fit();
"""


def _viewer(title: str, gray_png: bytes, width: int, height: int, overlay: str) -> str:
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>{escape(title)} · 标注影像</title>
<style>html,body{{height:100%;margin:0;background:#121417;color:#eee;font:14px system-ui,sans-serif}}
body{{display:flex;flex-direction:column}}header{{padding:10px 14px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}}
h1{{font-size:15px;margin:0 12px 0 0}}button{{cursor:pointer;padding:6px 12px;border:1px solid #777;border-radius:5px;background:#242930;color:#fff}}
small{{color:#bbb}}#viewer{{width:100%;flex:1;min-height:0;cursor:grab;touch-action:none;user-select:none}}
#viewer.dragging{{cursor:grabbing}}text{{font-family:system-ui,sans-serif}}</style>
<header><h1>{escape(title)}</h1><button id="zoom-out" aria-label="缩小">−</button><output id="zoom-value"></output>
<button id="zoom-in" aria-label="放大">＋</button><button id="fit">适应窗口</button><button id="actual">原始尺寸</button>
<small>滚轮缩放 · 拖动平移 · 双击复位 · 点大小保持不变 · 候＝待复核</small></header>
<svg id="viewer" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="带标注影像"
data-image-width="{width}" data-image-height="{height}"><g id="scene">
<image width="{width}" height="{height}" href="data:image/png;base64,{base64.b64encode(gray_png).decode('ascii')}"/>
{overlay}</g></svg><noscript>请允许此本地文件运行脚本以使用缩放，或打开同名 PNG 查看静态图片。</noscript>
<script>{_VIEWER_SCRIPT}</script></html>'''


def export_annotated_images(
    project: Project, out_dir: Path | None = None, entries: Iterable[CaseEntry] | None = None,
    adjust: ImageAdjust | None = None, progress: Callable[[int, int], None] | None = None,
) -> tuple[Path, int]:
    """Export all cases (including unfinished cases) without modifying project data.

    The caller must save current UI edits first. ``adjust`` is applied uniformly to
    the batch. An unreadable image aborts explicitly, preserving any existing ZIP.
    ``progress`` receives completed/total after each full image pair is written.
    """
    pool = list(project.sorted_cases() if entries is None else entries)
    out_dir = Path(out_dir) if out_dir is not None else project.exports_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = "annotated_images.zip"
    if entries is not None:
        selection = json.dumps([entry.case_id for entry in pool], ensure_ascii=False).encode("utf-8")
        filename = f"annotated_images_selected_{hashlib.sha256(selection).hexdigest()[:12]}.zip"
    destination = out_dir / filename
    with tempfile.NamedTemporaryFile(dir=out_dir, prefix=".annotated_images-", suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        manifest, links = [], []
        with ZipFile(temporary, "w", ZIP_DEFLATED, compresslevel=6) as archive:
            for ordinal, entry in enumerate(pool, 1):
                gray = load_gray(project.image_path(entry))
                if gray is None:
                    raise OSError(f"无法读取病例「{entry.display}」的图片：{project.image_path(entry)}")
                gray = apply_adjust(gray, adjust or ImageAdjust())
                ann = project.load_annotation(entry)
                shapes, marks, captions = _overlay(ann)
                overlay = _svg_overlay(shapes, marks, captions)  # validates finite coordinates before rasterization
                # Prefix prevents reserved Windows filenames, case-fold collisions and identical titles.
                title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", entry.display).strip(" .")[:90] or "case"
                stem = f"{ordinal:04d}_{title}"
                html_name, png_name = f"images/{stem}.html", f"images/{stem}.png"
                height, width = gray.shape
                archive.writestr(png_name, _render_png(gray, shapes, marks, captions))
                archive.writestr(html_name, _viewer(entry.display, _png_bytes(gray), width, height, overlay))
                manifest.append(dict(case_id=entry.case_id, title=entry.display, status=entry.status,
                                     width=width, height=height, point_count=len(marks),
                                     html=html_name, png=png_name))
                links.append(f'<li>{escape(entry.display)} · {len(marks)} 个点 · '
                             f'<a href="{quote(html_name)}">交互看片</a> · <a href="{quote(png_name)}">PNG 图片</a></li>')
                if progress:
                    progress(ordinal, len(pool))
            archive.writestr("index.html", '<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
                             '<title>标注影像</title><h1>标注影像</h1><p>请先解压整个压缩包，再打开本页。'
                             '选择「交互看片」，放大牙齿时标注点保持屏幕大小；PNG 为普通静态图片。</p><ul>'
                             + "".join(links) + '</ul></html>')
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            archive.writestr("使用说明.txt", "请先解压整个压缩包，然后双击 index.html。\n"
                             "每张片有 PNG 静态图片和可独立打开的 HTML 交互影像；无需联网、无需安装软件。\n"
                             "在 HTML 内用滚轮或加减按钮缩放，左键/中键拖动平移，双击恢复全图；标注点保持固定屏幕大小。\n"
                             "PNG 便于发送和打印，但普通看图软件放大 PNG 时，点也会放大。\n"
                             "颜色、当前牙框、分割轮廓和已保存标点来自项目；不补造遗漏点。未标注病例也包含原片。\n"
                             "HTML 点标签中的「候」与 PNG 标签的 * 表示尚待人工复核的自动候选。\n"
                             "坐标以同批导出的 sites.csv 为准；导出不会更改项目图片、坐标或已完成状态。\n")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination, len(pool)
