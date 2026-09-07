# PyInstaller 打包配置 —— Windows 与 macOS 共用一份
#
#   单文件（默认，发给别人用这个）：
#       .venv\Scripts\python.exe -m PyInstaller build.spec --noconfirm
#   单目录（自己天天用，启动快）：
#       set BUILD_MODE=onedir && .venv\Scripts\python.exe -m PyInstaller build.spec --noconfirm
#
# ⚠️ **发给别人一定要用单文件版**。单目录版的 exe 必须和旁边的 `_internal`
#    文件夹放在一起才能跑；只把 exe 发出去，对方会看到
#    「Failed to load Python DLL ... _internal\python314.dll」。
#    单文件版把 Python 解释器、Qt、OpenCV、numpy 全都塞进这一个 exe 里，
#    对方拿到直接双击，什么都不用装。

import os
import sys
from pathlib import Path

ROOT = Path(SPECPATH)
MAC = sys.platform == "darwin"
# macOS 只出 .app（内部就是目录结构），不出单文件 —— .app 本来就是一个
# 双击即用的包，再套单文件反而丢掉图标、Dock 名称和签名能力。
ONEFILE = (not MAC) and os.environ.get("BUILD_MODE", "onefile").lower() != "onedir"
APP_NAME = "牙槽骨吸收测量" + ("" if (ONEFILE or MAC) else "_文件夹版")

# ── 必须排除的模块 ──────────────────────────────────────────────────────
EXCLUDES = [
    # QtWebEngine 是最大杀手：解压后约 130MB，且即使代码里没用到，
    # PyInstaller 的 QtUiTools hook 也会通过 designer 插件把它拉进来
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel",
    "PySide6.QtUiTools",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQml",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.Qt3DCore",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtNetwork",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    # 开发期才用到的重型库，绝不进产物
    "scipy",
    "skimage",
    "sklearn",
    "matplotlib",
    "pandas",
    "torch",
    "torchvision",
    "ultralytics",
    "tkinter",
    "PIL",
    "IPython",
    "pytest",
    "setuptools",
    "pip",
    # onnxruntime 只在 models/ 里放了 .onnx 权重时才用得到（M5 阶段）。
    # 现在没有权重，打进去就是 35MB 的死重量；
    # segmenter.OnnxYoloSegmenter 已经能优雅降级（按钮灰显 + 提示安装）。
    # 将来要启用：把这行删掉，重新 build 即可。
    "onnxruntime",
]

# ── 逐个文件剔除的二进制（Analysis 之后过滤） ───────────────────────────
# 这些是被依赖分析顺带拖进来、但本程序一行都用不到的大件。
# 名字用「包含匹配」，所以同时命中 Windows 的 Qt6Network.dll 与
# macOS 的 QtNetwork.framework / libQt6Network.6.dylib。
DROP_BINARIES = [
    "opencv_videoio_ffmpeg",   # 29.4MB —— 视频编解码，本程序只读 PNG/JPG 静态图
    "opengl32sw",              # 19.7MB —— Mesa 软件 OpenGL 兜底（仅 Windows）
    "Qt6Network", "QtNetwork",  # ┐
    "libcrypto", "libssl",      # ├ 全程离线，不发任何网络请求
                                # ┘
    "Qt6Svg", "QtSvg", "qsvg",  # 只用位图，不加载 SVG 图标
]

a = Analysis(
    ["app/main.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=["openpyxl"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=1,
)


def _drop(entries):
    kept, dropped = [], []
    for entry in entries:
        name = entry[0].lower()
        if any(k.lower() in name for k in DROP_BINARIES):
            dropped.append(entry[0])
        else:
            kept.append(entry)
    for d in sorted(dropped):
        print(f"  [size] 剔除 {d}")
    return kept


a.binaries = _drop(a.binaries)
a.datas = _drop(a.datas)

pyz = PYZ(a.pure)

_common = dict(
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX 压 Qt 的 dll 容易触发杀软误报，得不偿失
    upx=False,
    console=False,      # 不要黑色控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

if ONEFILE:
    # 全部塞进一个 exe。启动时自解压到临时目录，比单目录慢几秒，
    # 但换来的是「发一个文件给对方，双击就能用」。
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **_common)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **_common)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False,
                   upx_exclude=[], name=APP_NAME)

    if MAC:
        # .app 包。CFBundleName 用中文没问题，但 bundle id 必须是 ASCII 反域名。
        app = BUNDLE(
            coll,
            name=f"{APP_NAME}.app",
            icon=None,
            bundle_identifier="com.periotools.boneloss",
            version=os.environ.get("APP_VERSION", "1.0.0"),
            info_plist={
                "CFBundleName": APP_NAME,
                "CFBundleDisplayName": APP_NAME,
                "CFBundleShortVersionString": os.environ.get("APP_VERSION", "1.0.0"),
                # 不声明的话在 Retina 上会被放大成马赛克
                "NSHighResolutionCapable": True,
                # 只读本地图片，不需要任何系统权限；声明一下省得 Gatekeeper 多问
                "LSApplicationCategoryType": "public.app-category.medical",
                "LSMinimumSystemVersion": "11.0",
                "NSRequiresAquaSystemAppearance": False,
            },
        )
