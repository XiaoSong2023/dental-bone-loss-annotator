# 本次集成源代码

同目录 `integration-source.zip` 包含两部分：

- `manual-app/`：用户原有 UI 与本次自动功能、保存/导出和 Windows 构建代码。
- `panodental-backend/`：本项目实现的模型适配、坐标变换、真实推理检查与依赖锁。

源代码包不包含患者影像、开发环境、训练数据、付费第三方源码或模型二进制。两份实际使用的权重已放在安装目录 models 下，固定版本和 SHA 见 models/README.md。没有重新为用户的既有软件指定开源许可证。

构建方法（Windows x64）：

1. GUI 使用 Python 3.14 与 `manual-app/requirements-ai-gui.txt`。
2. Worker 使用 Python 3.11；在 `panodental-backend` 执行 `uv sync --locked --extra dev --extra cpu --extra weight-audit`，保留 CPU 依赖索引。
3. 按 models/README.md 放置两份权重，安装 Inno Setup 6。`manual-app/scripts/build_ai_windows.ps1 -WorkerProject <panodental-backend目录>` 构建 GUI、Worker、合并目录与安装包。构建脚本需要各工程下的 `.venv/Scripts/python.exe`。
4. 开发启动 `manual-app/.venv/Scripts/python.exe -m app.main`；开发 GUI 的 worker 默认查找相邻审计工程目录，改布局时调整 `app/ui/ai_client.py:runtime_paths`。正式安装包使用自身 runtime 和 models 相对路径。

核心输入输出契约：`panodental.inference.analyze_image(image_path, model_dir, output_dir, progress=None, cancelled=None)`，output_dir 必须是新目录。`app.ai_worker` 封装为 UTF-8 JSONL 子进程协议。每次运行保留完整原始模型输出、变换、掩膜及模型哈希；GUI 合并后人工调整保持原始坐标和历史。

模型与运行库来源：

- 分割架构与官方 CPU 算子：[torchvision 0.21.0](https://github.com/pytorch/vision/tree/v0.21.0)，[PyTorch 2.6.0](https://github.com/pytorch/pytorch/tree/v2.6.0)。
- 分割发布者：[固定模型版本](https://huggingface.co/chocodo/teeth-segmentation-odontoai/tree/4867533fb8e8ccd115c10c533a238e4288757165)，模型卡 MIT；CLAHE、53 类头和 FrozenBatchNorm eps=0 已实际对照。
- 三点发布者：[固定模型版本](https://huggingface.co/rummanadib023/denpar-bone-loss-v2/tree/d254abd6df9ab41c0367b99457334d7f1ea69895)，ONNX 元数据 AGPL-3.0，导出版本 Ultralytics 8.4.92；[Ultralytics 源代码](https://github.com/ultralytics/ultralytics)，[许可原文](https://www.gnu.org/licenses/agpl-3.0.txt)。本包执行 ONNX，不执行发布者完整对象 PT。
- [ONNX Runtime 1.23.2](https://github.com/microsoft/onnxruntime/tree/v1.23.2)；Qt/PySide 与其余依赖的许可证和版本记录位于 THIRD_PARTY。

发布者未提供完整训练过程可复現材料。本包提供的是实际用于本次本地交付的集成源代码，不声称有上游未发布的原训练代码、训练集或医学准确率。
