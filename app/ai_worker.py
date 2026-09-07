"""Disposable CPU inference worker. Standard output is a UTF-8 JSON-lines protocol."""
from __future__ import annotations

import argparse
import contextlib
import json
import sys
import traceback
from pathlib import Path


def _backend():
    # The development GUI and CPU worker deliberately use different Python versions.
    if not getattr(sys, "frozen", False):
        source = (Path(__file__).resolve().parents[2]
                  / "0907牙周全景片分割及标注系统开发" / "panodental" / "src")
        if source.is_dir():
            sys.path.insert(0, str(source))
    from panodental import inference
    return inference


def health(model_dir: Path) -> dict:
    import platform
    import cv2
    import torch
    import torchvision
    import onnxruntime as ort
    from torchvision.ops import nms, roi_align

    backend = _backend()
    models = {}
    for name, spec in (("segmentation", backend.SEGMENTATION), ("keypoints", backend.POSE)):
        path = backend.verified_model_path(model_dir, spec)
        models[name] = {"path": str(path), "sha256": spec["sha256"], "verified": True}
    # Exercise the compiled CPU operators using a tiny engineering fixture; this is
    # runtime verification, never a dental prediction or model accuracy measurement.
    torch.set_num_threads(2)
    selected = nms(torch.tensor([[0., 0., 2., 2.], [0., 0., 2., 2.]]),
                   torch.tensor([.9, .8]), .5).tolist()
    pooled = roi_align(torch.ones((1, 1, 4, 4)), [torch.tensor([[0., 0., 3., 3.]])], 2)
    if selected != [0] or not torch.allclose(pooled, torch.ones_like(pooled)):
        raise RuntimeError("Torchvision CPU operators failed verification")
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(models["keypoints"]["path"], options,
                                   providers=["CPUExecutionProvider"])
    inputs, outputs = session.get_inputs(), session.get_outputs()
    if inputs[0].shape != [1, 3, 768, 768] or outputs[0].shape != [1, 14, 12096]:
        raise RuntimeError("Unexpected keypoint model input/output")
    return {"type": "health", "status": "ok", "frozen": bool(getattr(sys, "frozen", False)),
            "python": platform.python_version(), "device": "cpu", "cuda_required": False,
            "versions": {"torch": torch.__version__, "torchvision": torchvision.__version__,
                         "onnxruntime": ort.__version__, "opencv": cv2.__version__},
            "models": models, "cpu_nms": "passed", "cpu_roi_align": "passed",
            "pose_input_shape": inputs[0].shape, "pose_output_shape": outputs[0].shape,
            "providers": session.get_providers(), "training_steps": 0}


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description="PanoDental local CPU worker")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--mode", choices=("full", "segmentation", "keypoints"), default="full")
    parser.add_argument("--teeth", type=Path, help="Existing teeth snapshot for keypoints mode")
    parser.add_argument("--selftest", "--health", action="store_true", dest="selftest")
    args = parser.parse_args(argv)
    protocol = sys.stdout

    def emit(event):
        protocol.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")
        protocol.flush()

    try:
        with contextlib.redirect_stdout(sys.stderr):
            if args.selftest:
                report = health(args.models.resolve())
            else:
                if args.input is None or args.output is None:
                    raise ValueError("需要 --input 和 --output")
                result = _backend().analyze_image(
                    args.input.resolve(), args.models.resolve(), args.output.resolve(),
                    progress=lambda event: emit(dict(event, type="progress")), mode=args.mode,
                    teeth_path=args.teeth.resolve() if args.teeth else None)
                result_path = args.output.resolve() / "result.json"
                if result.get("status") != "completed" or not result_path.is_file():
                    raise RuntimeError("自动分析没有生成完整结果")
                report = {"type": "result", "result_path": str(result_path),
                          "run_id": result["run_id"]}
        emit(report)
        return 0
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        emit({"type": "error", "message": str(exc)})
        return 2


if __name__ == "__main__":
    from multiprocessing import freeze_support
    freeze_support()
    raise SystemExit(main())
