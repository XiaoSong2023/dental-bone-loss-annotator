"""GUI runs in its existing Qt environment; inference lives in a separate exe."""
from pathlib import Path

ROOT = Path(SPECPATH).parent
a = Analysis(
    [str(ROOT / "app/main.py")],
    pathex=[str(ROOT)],
    binaries=[], datas=[], hiddenimports=["openpyxl"],
    excludes=[
        "torch", "torchvision", "onnx", "onnxruntime", "panodental",
        "matplotlib", "scipy", "sklearn", "pandas", "pytest", "tkinter",
        "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineCore",
        "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia",
        "PySide6.QtUiTools", "PySide6.QtTest",
    ],
    noarchive=False, optimize=1,
)
# Qt 6.11 on Windows imports the OS ICU ABI (unversioned exports). A poppler
# icuuc.dll found on a developer's PATH has _78-suffixed exports and breaks QtCore.
# Never substitute that third-party ICU for the Windows system library.
a.binaries = [item for item in a.binaries
              if not any(name in item[0].lower()
                         for name in ("opencv_videoio_ffmpeg", "opengl32sw"))
              and Path(item[0]).name.lower() not in {"icuuc.dll", "icudt78.dll"}]
exe = EXE(PYZ(a.pure), a.scripts, [], exclude_binaries=True,
          name="牙槽骨吸收测量AI", console=False, debug=False,
          strip=False, upx=False, disable_windowed_traceback=False)
COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="PanoDentalAI")
