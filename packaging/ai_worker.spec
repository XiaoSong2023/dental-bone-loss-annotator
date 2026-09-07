"""Build with the Python 3.11 CPU model environment, never the GUI venv."""
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_dynamic_libs, copy_metadata

ROOT = Path(SPECPATH).parent
BACKEND = Path(os.environ["PANODENTAL_SOURCE"])
if not (BACKEND / "panodental/inference.py").is_file():
    raise RuntimeError("PANODENTAL_SOURCE must point to the audited backend src directory")

a = Analysis(
    [str(ROOT / "packaging/ai_worker_entry.py")],
    pathex=[str(ROOT), str(BACKEND)],
    binaries=collect_dynamic_libs("onnxruntime"),
    datas=copy_metadata("torch") + copy_metadata("torchvision")
          + copy_metadata("onnxruntime"),
    hiddenimports=["torchvision.ops", "torchvision.models.detection",
                   "onnxruntime.capi.onnxruntime_pybind11_state"],
    excludes=["PySide6", "PyQt5", "PyQt6", "matplotlib", "pytest",
              "tkinter", "IPython", "onnx", "tensorboard", "pandas",
              "scipy", "sklearn", "cv2.qt"],
    noarchive=False, optimize=1,
)
a.binaries = [item for item in a.binaries
              if "opencv_videoio_ffmpeg" not in item[0].lower()]
exe = EXE(PYZ(a.pure), a.scripts, [], exclude_binaries=True,
          name="PanoDentalWorker", console=True, debug=False,
          strip=False, upx=False)
COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="runtime")
