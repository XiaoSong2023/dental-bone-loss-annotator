"""Old projects remain in place; engineering fixtures contain no patient data."""
import hashlib
import json
from pathlib import Path

import pytest

from app.core import project_discovery
from app.core.project import Project, STATUS_DONE


def snapshot(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def legacy_project(root, schema, archived):
    root.mkdir()
    relative = "done/001.png" if archived else "001.png"
    image = root / "images" / relative
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image-preservation-fixture")
    (root / "annotations").mkdir()
    site = {"surface": "mesial", "cej": {"x": 10, "y": 20},
            "cej2": {"x": 11, "y": 22}, "ac": {"x": 12, "y": 24},
            "apex": {"x": 15, "y": 90}}
    tooth = {"fdi": 16, "roi": [5, 10, 30, 90], "sites": [site]}
    if schema == 1:
        tooth["apex"] = site.pop("apex")
    annotation = {"schema_version": schema, "image": {"file": relative},
                  "patient": {"id": "001_升级测试", "age": 61, "sex": "女", "note": "人工备注"},
                  "teeth": [tooth], "meta": {"status": "done"}}
    (root / "annotations" / "001.json").write_text(json.dumps(annotation), encoding="utf-8")
    index = {"version": 1, "name": "旧版工程夹具", "settings": {"physical_archive": archived},
             "cases": [{"case_id": "001", "image": relative, "status": "done",
                        "annotated_teeth": 1, "title": "已登记姓名"}]}
    (root / "project.json").write_text(json.dumps(index), encoding="utf-8")
    return root


@pytest.mark.parametrize("schema", [1, 2, 3, 5])
@pytest.mark.parametrize("archived", [False, True])
def test_open_and_save_old_done_case_preserves_demographics_points_and_image(tmp_path, schema, archived):
    root = legacy_project(tmp_path / "legacy", schema, archived)
    before = snapshot(root)
    project = Project.open(root)
    entry = project.by_status(STATUS_DONE)[0]
    ann = project.load_annotation(entry)
    assert len(project.cases) == 1 and project.counts()[STATUS_DONE] == 1
    assert project.next_unfinished() is None
    assert entry.display == "已登记姓名"
    assert ann.patient.id == "001_升级测试"
    assert ann.patient.age == 61 and ann.patient.sex == "女" and ann.patient.note == "人工备注"
    tooth = ann.teeth[0]
    assert tooth.roi == (5, 10, 30, 90)
    assert [tooth.site("mesial").get(role).as_tuple() for role in ("cej", "cej2", "ac", "apex")] == [
        (10, 20), (11, 22), (12, 24), (15, 90)]
    assert snapshot(root) == before  # Opening/migrating the model is read-only.
    project.save_annotation(entry, ann)
    reopened = Project.open(root)
    again = reopened.load_annotation(reopened.cases[0])
    assert reopened.cases[0].status == again.status == "done"
    assert reopened.cases[0].image == entry.image
    assert again.patient == ann.patient and again.teeth[0].roi == tooth.roi
    assert again.teeth[0].site("mesial").points_map() == tooth.site("mesial").points_map()
    assert project.image_path(entry).read_bytes() == b"image-preservation-fixture"


@pytest.mark.parametrize("existing", ["project.json", "annotations/001.json", "images/done/001.png"])
def test_create_refuses_to_overwrite_any_existing_project_material(tmp_path, existing):
    root = tmp_path / "existing"
    original = root / existing
    original.parent.mkdir(parents=True)
    original.write_bytes(b"existing material must survive")
    before = snapshot(root)
    with pytest.raises(FileExistsError, match="打开项目"):
        Project.create(root)
    assert snapshot(root) == before


@pytest.mark.parametrize("content", [None, "{truncated", "[]", '{"cases": null}',
                                    '{"version": 999, "cases": []}', '{"cases": [{}]}'])
def test_open_invalid_index_never_recreates_or_overwrites_files(tmp_path, content):
    root = tmp_path / "invalid"
    (root / "images").mkdir(parents=True)
    (root / "images" / "keep.png").write_bytes(b"keep")
    if content is not None:
        (root / "project.json").write_text(content, encoding="utf-8")
    before = snapshot(root)
    with pytest.raises(ValueError):
        Project.open(root)
    assert snapshot(root) == before


def test_discovery_uses_only_known_roots_without_touching_or_moving_projects(tmp_path, monkeypatch):
    last = legacy_project(tmp_path / "custom", 3, True)
    registered = legacy_project(tmp_path / "registered", 1, False)
    local = tmp_path / "local"
    default = local / "Programs" / "牙槽骨吸收测量"
    default.parent.mkdir(parents=True)
    legacy_project(default, 3, False)
    legacy_project(default / "unrelated-child", 3, False)
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setattr(project_discovery, "_registered_install_dirs", lambda: [registered, last])
    before = snapshot(tmp_path)
    found = project_discovery.discover_existing_projects(last)
    assert found == [last.resolve(), registered.resolve(), default.resolve()]
    assert snapshot(tmp_path) == before
    assert project_discovery.discover_existing_projects(tmp_path / "missing") == [
        registered.resolve(), last.resolve(), default.resolve()]


def test_installer_only_updates_application_payload_and_shortcuts():
    script = (Path(__file__).resolve().parents[1] / "installer_ai.iss").read_text(encoding="utf-8")
    sections = {}
    section = None
    for line in script.splitlines():
        if line.startswith("["):
            section = line
            sections[section] = []
        elif line and not line.startswith(";") and section is not None:
            sections[section].append(line)
    sources = [line.split('"')[1] for line in sections["[Files]"]]
    assert "{#SrcDir}\\*" not in sources
    assert {source.split("\\")[1] for source in sources} == {
        "{#AppExe}", "使用说明.md", "_internal", "runtime", "models", "SOURCE", "THIRD_PARTY"}
    assert "UsePreviousAppDir=yes" in sections["[Setup]"]
    assert "[UninstallDelete]" not in sections and "[Registry]" not in sections
    assert all("{app}" not in line and "filesandordirs" not in line
               for line in sections["[InstallDelete]"])
    assert all("unins" not in line.lower() for line in sections["[Run]"])
