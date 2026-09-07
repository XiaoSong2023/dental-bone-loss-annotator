"""Protocol fixtures only; trained-model correctness is tested in the CPU backend."""
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest

from app import ai_worker
from app.ui.ai_client import AiClient


def test_worker_passes_exact_keypoints_snapshot_to_backend(tmp_path, monkeypatch, capsys):
    image, teeth, out = tmp_path / "input.png", tmp_path / "teeth.json", tmp_path / "output"
    calls = []
    def analyze(inp, models, output, **kwargs):
        calls.append((inp, models, output, kwargs))
        output.mkdir()
        (output / "result.json").write_text("{}")
        return {"status": "completed", "run_id": "protocol-fixture"}
    monkeypatch.setattr(ai_worker, "_backend", lambda: SimpleNamespace(analyze_image=analyze))
    assert ai_worker.main(["--input", str(image), "--models", str(tmp_path), "--output", str(out),
                           "--mode", "keypoints", "--teeth", str(teeth)]) == 0
    assert calls[0][3]["mode"] == "keypoints"
    assert calls[0][3]["teeth_path"] == teeth.resolve()
    assert json.loads(capsys.readouterr().out)["type"] == "result"


def test_client_transmits_keypoints_mode_and_snapshot_path(qtbot, tmp_path):
    script = tmp_path / "protocol_fixture.py"
    script.write_text("""import argparse,json,pathlib
p=argparse.ArgumentParser()
for key in ('input','models','output','mode','teeth'): p.add_argument('--'+key,required=True)
a=p.parse_args()
assert a.mode=='keypoints'
assert pathlib.Path(a.teeth).is_file()
out=pathlib.Path(a.output); out.mkdir()
result=out/'result.json'; result.write_text(json.dumps(vars(a)))
print(json.dumps({'type':'result','result_path':str(result)}),flush=True)
""", encoding="utf-8")
    teeth = tmp_path / "existing teeth.json"
    teeth.write_text("{}")
    client = AiClient()
    with qtbot.waitSignal(client.completed, timeout=5000):
        client.start(tmp_path / "input.png", tmp_path / "output", command=[sys.executable, str(script)],
                     cwd=tmp_path, models=tmp_path, mode="keypoints", teeth_path=teeth)
    transmitted = json.loads((tmp_path / "output/result.json").read_text())
    assert Path(transmitted["teeth"]) == teeth.resolve()
    assert transmitted["mode"] == "keypoints" and not client.busy


def test_client_requires_snapshot_only_for_keypoints(qtbot, tmp_path):
    client = AiClient()
    for mode, teeth in (("keypoints", None), ("keypoints", tmp_path / "missing"),
                        ("segmentation", tmp_path), ("full", tmp_path)):
        with pytest.raises(ValueError):
            client.start(tmp_path / "input.png", tmp_path / "output", mode=mode, teeth_path=teeth)
        assert not client.busy
