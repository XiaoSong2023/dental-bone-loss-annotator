# Mac 开发接力包 · 1.4.0-preview

此 ZIP 是继续开发用的源码和已训练模型，不是 Mac 安装包。Windows 的 EXE、DLL、虚拟环境不能搬到 Mac 直接运行。当前版本的实际开发与验证平台是 Windows；尚未在 Mac 构建或验证，未产出本版本 `.app` / `.dmg`。

最新用户要求是完成 Windows 本轮功能后，到 Mac 继续开发。本文件覆盖旧文档中“取消 Mac 开发”等历史平台说明。不要把旧 README 的人工版 Mac 打包说明当作完整 AI 版已能打包的证明。

## 解压后的目录

|目录|用途|
|---|---|
|`gui/`|当前统一版 GUI 的 Git 跟踪源码、测试、依赖说明、使用说明和打包脚本；程序入口 `app/main.py`|
|`backend/`|当前真实 CPU 推理后端源码、测试、`pyproject.toml`、`uv.lock` 与模型契约文档；实际推理入口 `src/panodental/inference.py`|
|`models/`|本版本实际使用的两份已训练权重，文件名与子目录保持原样；来源和 SHA-256 见同目录 README|
|`THIRD_PARTY/models/`|模型卡与现有许可声明；Qt 许可源文档另在 `gui/packaging/licenses/Qt/`|
|`MANIFEST.json`|全部入包文件的 SHA-256、字节数、源仓库提交号，以及打包时是否有未提交修改|

包内不包含任何患者影像、名册、标注项目、导出结果、reports、inputs、训练数据、`.git` 历史、虚拟环境或 Windows 程序载荷。测试代码中自行生成的工程样例不代表临床真值。

已有病例也要搬到 Mac 时，应由用户另行复制完整项目文件夹，保留 `project.json` 及其引用的图片、annotations、config 等目录，不要只复制 exports，也不要放进 `.app` 内。本开发包不会读取、移动或清理现有病例。

## 先在 Mac 建环境和启动源码

1. 确认 Mac 是 Apple Silicon（arm64）还是 Intel（x86_64），记录 macOS、Python 版本与可用内存。先采用原生架构 Python 3.11，因为后端目前要求 `>=3.11,<3.12`；不能把 Windows Python 3.14 GUI 环境原样复制过来。
2. 在包根目录建立两个新环境，保持界面和推理依赖隔离。以下是接力时执行的开发命令，当前 Windows 会话未在 Mac 执行这些命令；依赖安装需要 Mac 能获取适合其架构的 wheel。

```bash
python3.11 -m venv gui/.venv
gui/.venv/bin/python -m pip install -r gui/requirements.txt pytest pytest-qt
python3.11 -m venv backend/.venv
backend/.venv/bin/python -m pip install 'numpy==1.26.4' 'Pillow==11.3.0' \
  'pydantic==2.11.7' 'torch==2.6.0' 'torchvision==0.21.0' \
  'onnxruntime==1.23.2' 'opencv-python-headless==4.11.0.86'
backend/.venv/bin/python -m pip install --no-deps -e backend
```

这些后端版本来自当前 Windows 已验证组合，`torch/torchvision` 去掉 Windows 的 `+cpu` 后缀作为 Mac 首次解析候选，**不是已经验证的 Mac 依赖锁**。若目标架构没有匹配 wheel，停止安装并记录报错后选择可兼容组合，不要改用 CUDA 或静默切换模型。`requirements-ai-worker.txt` 和 `backend/pyproject.toml` 的 `cpu` extra / `uv.lock` 仍是 Windows CPU 配置，不要在 Mac 直接 `uv sync --locked --extra cpu`。这里使用 `--no-deps` 安装后端源码，是为了不顺带装后端旧原型界面的全套 PySide6；正式后端 GUI 测试环境需另外安装对应 Qt 和测试依赖。

```bash
cd gui
.venv/bin/python -m app.main
```

这一命令用于首先验证当前 GUI 能在 Mac 建窗、打开项目及手动标注。**自动分割/自动标注尚需下一节的 worker 路径适配，不能把建窗成功视为 AI 已接通。**

在包根目录可先独立验证 worker 和模型文件：

```bash
cd gui
../backend/.venv/bin/python -m app.ai_worker --models ../models --health
```

这项检查验证已训练权重的 SHA-256、Torchvision CPU NMS/ROIAlign 和 ONNX 输入输出，不读取患者片，也不进行训练。成功仍需再用一张用户授权的真实全景片验证“分割 → 点击独立自动标注 → 原图坐标还原 → 保存/重开 → 两个坐标文件和图片 ZIP 导出”，与 Windows 结果比较。

## 完整 AI 版尚需的 Mac 适配

- `gui/app/ui/ai_client.py::runtime_paths()`：源码模式仍寻找相邻 Windows 工作区的 `.venv/Scripts/python.exe`，frozen 模式仍寻找 `runtime/PanoDentalWorker.exe`。Mac 应定位到 `backend/.venv/bin/python`、包根 `models/`，保持 `cwd=gui` 及 GUI 模块可导入；封装后要从实际 `.app` 内资源/worker 位置解析。不能仅改文件后缀后就声明可用。
- `gui/app/ai_worker.py::_backend()` 有原 Windows 工作区源码路径兜底；上面的后端 `pip install --no-deps -e backend` 可让独立 worker 从自身环境加载后端，打包时仍需显式收集 `panodental`。
- CPU 是当前基线：Torch 在 CPU 加载分割权重，ONNX 固定 `CPUExecutionProvider`，无需 NVIDIA / CUDA。MPS 加速、Intel Mac 的依赖可用性、真实峰值内存与速度都要在目标 Mac 实测；当前后端的峰值内存辅助函数在非 Windows 返回 `None`，不影响其自身控制流，但 Mac 内存测试需补测。
- 分割采用严格结构和固定 SHA 的 `best.pth`；关键点采用 `surf_pose.onnx`。两份均已训练，本次集成训练步数为 0。开发包没有训练集、关键点原生训练检查点或训练流水线验收，不能承诺直接继续训练。保留原始预测和人工修订，CEJ-2mm 仍不能以固定像素比例伪造。

## 现有 Mac 打包代码与缺项

`gui/build_macos.sh`、`gui/build.spec` 的 macOS 分支、`.github/workflows/build.yml` 是旧人工版遗留脚本。它们可作为打包参考，但当前旧脚本排除了 Torch/ONNXRuntime 等，并未将独立 AI worker 和这两份真实模型一起封装；构建脚本还会清除自身 `build/dist`。不要直接执行它来交付当前 AI 完整版，也不要据其日志忽略自检失败。

接力应在目标 Mac 完成两个本地 PyInstaller 环境、GUI `.app` 与独立 CPU worker 的构建；收集 Qt 插件、PyTorch/Torchvision/ONNXRuntime 原生库和模型，修正 `.app` 内路径，验证 worker 的可执行权限与工作目录。之后再验证双击启动、独立分割/标注按钮、人工修改、名册首人资料、导出图片缩放、旧项目已完成状态保留，最后制作 DMG。需要对外分发时再完成 Apple 签名、公证和实际目标系统安装验收；当前没有这些凭据或验收结果。

这是本地传输任务，不需要上传 GitHub，不应触发包内旧 CI 的自动发布。模型卡声明与现有 AGPL-3.0 / Qt 许可材料原样附带，不据此替作者授予额外许可；Mac 分发时需重新收集实际 Mac 依赖的许可清单。

## Windows 端生成此接力包

先提交本轮源码，再运行。脚本只读取 Git 跟踪的源码白名单和明确列出的模型/许可文件，会检查两份权重 SHA-256、拒绝链接文件及已存在的输出 ZIP；无下载、无训练、无患者数据复制。

```powershell
.\.venv\Scripts\python.exe scripts/package_mac_handoff.py `
  --backend 'D:\Codex 项目集合\0907牙周全景片分割及标注系统开发\panodental' `
  --dry-run
.\.venv\Scripts\python.exe scripts/package_mac_handoff.py `
  --backend 'D:\Codex 项目集合\0907牙周全景片分割及标注系统开发\panodental' `
  --output 'dist\Mac-handoff\PanoDental-Mac-Development-1.4.0-preview.zip'
```

源码包不包含 Git 历史；在 Mac 继续开发时可重新 `git init`，以包内 MANIFEST 的提交号与 SHA-256 作为来源记录。实际验证进度以本轮 `gui/STATUS.md`、`gui/HANDOFF.md` 为准，每轮继续更新这两个文件。
