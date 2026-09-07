# HANDOFF — 2026-09-07

本目录是用户指定的最终 UI 整合工程；原始开发任务书、购买 ZIP、社区权重搜索和模型审计仍在相邻 `0907牙周全景片分割及标注系统开发`。先读本目录 STATUS.md、models/README.md 与原工程 panodental/docs/MODEL_CONTRACTS.md。不要重新生成任务规划，也不要再索要已确认不存在的原项目权重或 Mac。

用户最新授权：选择适合的社区权重整合，必要时可训练。首版已经使用两份真实训练权重运行，训练不是功能启动前置条件。没有CUDA要求；无正式训练、云训练或影像上传。后续若需要每牙完整/可靠三点，需要全景片三点标签、独立测试集与域适配，不得填几何假点。

## 工程分工与关键契约

- `app/ui/main_window.py`：当前病例绑定、运行快照、回调合并、状态与保存；`ai_client.py` 管理 QProcess 及UTF8 JSONL、取消和子进程日志。
- `app/ai_worker.py`：独立CPU入口；开发调用相邻工程3.11 Python，安装版调用自身 runtime/PanoDentalWorker.exe。GUI为3.14，两个Python环境不要混装。
- 后端在相邻工程 `panodental/src/panodental/inference.py`；`analyze_image(image_path,model_dir,output_dir,progress=None,cancelled=None)`。output_dir必须不存在；result.json与raw mask/pose/transform完整保留。JSON坐标全部回原图，无真值框输入。
- `app/core/ai_merge.py`：事务合并，新run ID，原图坐标校验、一对一牙框匹配、raw点与人工点分离、拒绝点不补回、左右侧未确认。`cej`→cej，`bone_level`→ac，`apex`→apex，cej2不生成。
- `models.py` schema4的Pt、Site.point_meta、Tooth.roi_corners/candidate_surfaces/segmentation、CaseAnnotation.ai_runs；JSON浮点不舍入，导出显示可格式化。旧文件迁移不更改测量公式。
- `storage.py` 原子保存并拒绝未来版本，`export.py` 额外输出 boxes.csv / Excel牙框坐标 / JSON四角与来源。
- 整个项目文件夹一起搬移，必须包括 runs。raw结果不随人工编辑改写。不要把单独JSON导出误称包含全部mask二进制的项目包。

## 运行与构建

GUI源环境：`.venv/Scripts/python.exe -m app.main`。

CPU环境在相邻 `panodental/.venv`；需要重建时运行 `uv sync --locked --extra dev --extra cpu --extra weight-audit`，仅 uv sync 会移除CPU extras。不要在GUI 3.14环境装Torch。

测试：GUI环境运行 `python tests/test_core.py`、`python tests/test_smoke.py`；新回归使用 pytest（不是 unittest 通配全部）：`uv pip install --python .venv/Scripts/python.exe pytest==8.4.2 pytest-qt==4.5.0`，然后 `python -m pytest tests/test_ai_core.py tests/test_ai_ui.py -q`。开发测试依赖不进入安装包。已在目标Python3.14/PySide6 6.11.2环境合跑21项全部通过。真实UI探针是 `tests/probe_real_ui.py`，不计入普通单测、不使用模拟预测证明医学效果。

构建：`scripts/build_ai_windows.ps1`，可分 Worker、Gui、Assemble、Installer 阶段。先代码定稿，再 `scripts/package_source.py --backend <相邻panodental目录>` 更新安装随附源包，之后Assemble与Installer。依赖锁、许可证收集和新AppId Inno安装器均在仓库，旧dist不覆盖。

## 结果解释与后续

JPG后端v3 31牙/17组三点，GUI结果导入取每图像半侧最高分组后为16组；这是候选数量，不是准确率。GUI输入的8bit灰度PNG与原JPG不同，以最终安装验证报告记录的数量为准。左/右仅是图像侧，必须人工确认解剖侧别。局部裁剪不能使全景片自动具有根尖片成像特征；尚无跨域准确率保证。

尚未完成：全景片数据上的独立医学准确率评估、每牙三点覆盖保证、ONNX对原生PT数值对照（未执行完整对象pickle）、Mac版（用户取消）、外部分发许可审查。原模型缺的配套参数仍未出现，采用社区模型不代表拿到了原论文权重。

最终交付已完成：`dist/AI-integrated/牙槽骨吸收测量AI_安装包_v1.1.0-ai-preview.exe`，SHA256 `f637c083a4d020ca4efdfd648644454f5af137ff27fa957be7e37cba551869e5`。安装目录为 `C:/Users/Lenovo/AppData/Local/Programs/牙槽骨吸收测量AI`，桌面有新AI快捷方式，原手工版保留。

`reports/installed-gui-e2e/report.json` 是直接操纵真实目录版窗口完成的整条链路与三种菜单导出，输入为GUI灰度PNG，58.30秒、1.48GiB峰值，31牙/17原始组/16显示组48点，覆盖11牙。安装版逐文件SHA与该目录版一致，另外完成净PATH启动与冻结Worker健康；不是在安装版再次重复点击推理。原生UI树对Windows文件选择器的焦点描述有误，实际通过窗口截图定位输入框成功操作，不是产品故障。

打包失败根因已修复：工具宿主PATH带入poppler ICU及libheif运行库。构建必须保留净PATH与--clean，不能只清运行时PATH；不要把旧失败包当最终包。打包提交86a32ef/a0c870d，核心90919c2，UI64b88d9，原后端6836cee；最新文档提交以git log为准。

安装、自检、文件一致性集中证据在 `reports/packaging-validation-summary.json`。当前无构建/推理后台任务，不必重复已经通过的真实推理。质量未验证项仍按上文保留。每轮继续更新STATUS/HANDOFF。
