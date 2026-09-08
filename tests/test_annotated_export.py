"""Export fidelity and offline viewer geometry; engineering fixtures, no inference."""

from __future__ import annotations

import base64
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from zipfile import ZipFile

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.annotated_export import _VIEWER_SCRIPT, export_annotated_images
from app.core.models import Pt
from app.core.project import Project, STATUS_DONE
from app.imaging.loader import ImageAdjust, imwrite_unicode, load_gray


@pytest.fixture
def project(tmp_path):
    project = Project.create(tmp_path / "项目")
    for index in range(3):
        source = tmp_path / f"{index+1:03d}_测试图.png"
        image = np.full((130, 210), 40+index*20, dtype=np.uint8)
        image[0, 0] = index
        assert imwrite_unicode(source, image)
        entries, skipped = project.import_paths([source])
        assert len(entries) == 1 and not skipped
    first = project.cases[0]
    ann = project.load_annotation(first)
    tooth = ann.add_tooth(16, (20.125, 25.75, 110.5, 80.0))
    tooth.initial_auto_roi = (1, 1, 10, 10)
    tooth.segmentation = {"contours": [[[22.25, 28.75], [120.125, 30.5], [87.25, 100.75]]]}
    site = tooth.site("mesial")
    site.cej = Pt(50.125, 45.75)
    site.cej2 = Pt(52.25, 55.5)
    site.ac = Pt(58.125, 70.75)
    site.apex = Pt(70.875, 95.25)
    site.point_meta = {"cej": {"origin": "model", "raw_xy": [199, 129], "review_status": "pending"}}
    tooth.site("distal").cej = Pt(150, 70)
    tooth.site("distal").skipped = True
    project.save_annotation(first, ann)
    project.settings.physical_archive = True
    project.set_status(first, STATUS_DONE)
    return project


def _contents(path):
    with ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _embedded_gray(html):
    encoded = re.search(r'href="data:image/png;base64,([^"]+)"', html).group(1)
    return cv2.imdecode(np.frombuffer(base64.b64decode(encoded), np.uint8), cv2.IMREAD_GRAYSCALE)


def test_archive_covers_completed_and_unmarked_without_modifying_project(project):
    before = {p: p.read_bytes() for p in project.root.rglob("*") if p.is_file()}
    calls = []
    path, count = export_annotated_images(project, progress=lambda done, total: calls.append((done, total)))
    assert path == project.exports_dir / "annotated_images.zip"
    assert count == 3 and calls == [(1, 3), (2, 3), (3, 3)]
    files = _contents(path)
    manifest = json.loads(files["manifest.json"])
    assert len(files) == 9  # six image files + index, manifest, instructions
    assert [m["point_count"] for m in manifest] == [4, 0, 0]
    assert manifest[0]["status"] == STATUS_DONE
    for entry, metadata in zip(project.sorted_cases(), manifest):
        png = cv2.imdecode(np.frombuffer(files[metadata["png"]], np.uint8), cv2.IMREAD_COLOR)
        assert png.shape == (130, 210, 3)
        html = files[metadata["html"]].decode("utf-8")
        assert np.array_equal(_embedded_gray(html), load_gray(project.image_path(entry)))
        if metadata["point_count"] == 0:
            assert np.array_equal(png[:, :, 0], _embedded_gray(html))
            assert 'class="mark"' not in html
    for p, content in before.items():
        assert p.read_bytes() == content
    assert project.cases[0].status == STATUS_DONE
    assert project.cases[0].image.startswith("done/")


def test_saved_fractional_points_current_box_and_contour_match_source(project):
    path, _ = export_annotated_images(project)
    files = _contents(path)
    metadata = json.loads(files["manifest.json"])[0]
    html = files[metadata["html"]].decode("utf-8")
    svg = ET.fromstring(re.search(r'(<svg .*?</svg>)', html, re.S).group(1))
    ns = {"svg": "http://www.w3.org/2000/svg"}
    marks = svg.findall('.//svg:g[@class="mark"]', ns)
    ann = project.load_annotation(project.cases[0])
    tooth = ann.teeth[0]
    assert len(marks) == 4
    for mark in marks:
        role = mark.attrib["data-role"]
        pt = tooth.site("mesial").get(role)
        assert (float(mark.attrib["data-x"]), float(mark.attrib["data-y"])) == pt.as_tuple()
    polygons = svg.findall('.//svg:polygon', ns)
    assert polygons[0].attrib["points"] == "22.25,28.75 120.125,30.5 87.25,100.75"
    assert polygons[1].attrib["points"] == "20.125,25.75 130.625,25.75 130.625,105.75 20.125,105.75"
    assert all(p.attrib["stroke"] == tooth.color for p in polygons)
    assert all(p.attrib["vector-effect"] == "non-scaling-stroke" for p in polygons)
    assert "P1·候" in html and "待复核候选" in html
    assert "raw_xy" not in html and 'data-x="199.0"' not in html
    preview = cv2.imdecode(np.frombuffer(files[metadata["png"]], np.uint8), cv2.IMREAD_COLOR)
    # The colored crosshair extends 11 px from the saved CEJ, at original dimensions.
    b, g, r = preview[46, 40]
    assert int(b) > int(r) + 70 and int(g) > int(r) + 70


def test_titles_are_escaped_and_duplicate_names_do_not_overwrite(project):
    title = '../CON/<script>alert("x")</script>&\x01'
    for entry in project.cases:
        entry.title = title
    path, count = export_annotated_images(project)
    files = _contents(path)
    manifest = json.loads(files["manifest.json"])
    assert count == 3
    assert len({m["html"].casefold() for m in manifest}) == 3
    assert all(".." not in Path(m["html"]).parts and m["html"].count("/") == 1 for m in manifest)
    for metadata in manifest:
        html = files[metadata["html"]].decode("utf-8")
        assert html.count("<script>") == 1
        assert '<script>alert("x")</script>' not in html
        assert '&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;' in html
        assert "fetch(" not in html
    assert b"<script>" not in files["index.html"]


def test_selected_export_does_not_overwrite_full_batch(project):
    full, _ = export_annotated_images(project)
    before = full.read_bytes()
    selected, count = export_annotated_images(project, entries=[project.cases[1]])
    assert selected != full and count == 1
    assert full.read_bytes() == before
    assert len(json.loads(_contents(selected)["manifest.json"])) == 1


def test_bad_image_keeps_previous_package_and_reports_case(project):
    path, _ = export_annotated_images(project)
    previous = path.read_bytes()
    project.image_path(project.cases[1]).unlink()
    with pytest.raises(OSError, match="002_测试图"):
        export_annotated_images(project)
    assert path.read_bytes() == previous
    assert not list(project.exports_dir.glob(".annotated_images-*.tmp"))


def test_adjustment_applies_to_export_without_changing_image(project):
    entry = project.cases[2]
    original = project.image_path(entry).read_bytes()
    path, _ = export_annotated_images(project, entries=[entry], adjust=ImageAdjust(invert=True))
    files = _contents(path)
    metadata = json.loads(files["manifest.json"])[0]
    displayed = _embedded_gray(files[metadata["html"]].decode("utf-8"))
    assert np.array_equal(displayed, 255-load_gray(project.image_path(entry)))
    assert project.image_path(entry).read_bytes() == original


def test_empty_project_has_no_fabricated_images(tmp_path):
    path, count = export_annotated_images(Project.create(tmp_path / "empty"))
    files = _contents(path)
    assert count == 0
    assert json.loads(files["manifest.json"]) == []
    assert not any(name.startswith("images/") for name in files)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node needed to execute shipped viewer JavaScript")
def test_shipped_zoom_and_pan_script_keeps_point_screen_size(tmp_path):
    # Execute the actual shipped script, with minimal DOM stand-ins. Parent QA also
    # exercises a real browser; this test guards transform math and event wiring.
    script = r'''
const assert = require('node:assert/strict');
const handlers = {}, attributes = {};
const glyph = {setAttribute: (k,v) => attributes.glyph=v};
const svgStub = {dataset:{imageWidth:'2000',imageHeight:'1000'}, clientWidth:1000, clientHeight:600,
 addEventListener:(name,fn)=>handlers[name]=fn, getBoundingClientRect:()=>({left:0,top:0}),
 setPointerCapture:()=>{},classList:{add:()=>{},remove:()=>{}}};
const elements = {viewer:svgStub,scene:{setAttribute:(k,v)=>attributes.scene=v},
 'zoom-value':{},fit:{},'zoom-in':{},'zoom-out':{},actual:{}};
global.document={getElementById:id=>elements[id],querySelectorAll:()=>[glyph]};
global.window={addEventListener:()=>{}};
''' + _VIEWER_SCRIPT + r'''
function close(a,b) { assert.ok(Math.abs(a-b)<1e-7, `${a} != ${b}`); }
function checkPointSize() {
 const inverse=Number(attributes.glyph.match(/scale\(([^)]+)\)/)[1]);
 close(5*inverse*scale,5); close(11*inverse*scale,11);
}
checkPointSize();
const px=600,py=300, imageX=(px-tx)/scale,imageY=(py-ty)/scale;
for(let i=0;i<8;i++){ zoomAt(1.4,px,py); checkPointSize(); }
close(imageX*scale+tx,px); close(imageY*scale+ty,py);
elements['zoom-out'].onclick();checkPointSize();
const wheelImageX=(px-tx)/scale,wheelImageY=(py-ty)/scale;
handlers.wheel({preventDefault(){},shiftKey:false,ctrlKey:true,deltaX:0,deltaY:90,deltaMode:0,clientX:px,clientY:py});
checkPointSize();close(wheelImageX*scale+tx,px);close(wheelImageY*scale+ty,py);
const oldTx=tx,oldTy=ty;
handlers.pointerdown({button:0,pointerId:1,clientX:20,clientY:30,preventDefault(){}});
handlers.pointermove({pointerId:1,clientX:80,clientY:45});
close(tx-oldTx,60);close(ty-oldTy,15);checkPointSize();
handlers.pointerup();assert.equal(drag,null);
elements.actual.onclick();close(scale,1);checkPointSize();
elements.fit.onclick();checkPointSize();
console.log('viewer zoom, anchor, pan and fixed glyph size passed');
'''
    source = tmp_path / "viewer-test.cjs"
    source.write_text(script, encoding="utf-8")
    result = subprocess.run([shutil.which("node"), str(source)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
