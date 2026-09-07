# HANDOFF — 2026-09-07

## 当前交付

1.2.0-preview 已构建、原位安装并完成验收。用户要的两种入口共用原UI：桌面“牙槽骨吸收测量AI”运行full，桌面“牙槽骨吸收测量（分割人工版）”运行manual。直接打开exe默认manual。原手工1.0保留。不要重新生成开发规划、再索要已确认缺失的原项目权重或Mac环境。

本目录是最终UI工程；原任务书、购买源码、权重审计及模型后端在相邻 `0907牙周全景片分割及标注系统开发/panodental`。最新功能说明见 `docs/CONTOUR_REVIEW.md` 与 `packaging/distribution/使用说明.md`；历史验收保留在STATUS.md后半。

本轮不训练、不改模型权重、不降阈值、不编造点。真实样片仍31牙；完整自动模式由17组三点/11牙改善到23组69点/15牙，16牙仍无完整组。UI按图像半侧保留20组60点，其余原始候选保存在run结果。轮廓残差最大1.14e-13px仅证明几何贴线，不证明CEJ或真正骨嵴顶准确，尤其骨嵴顶不一定在牙齿边界。不得把全景片裁剪称为真实根尖片，也不得把QA人工点作医学标注真值。

## 功能与代码契约

- 原四点cej、cej2、ac、apex及四公式不变。纯分割模式不加载ORT/pose权重、不产生候选点，双击机器牙框直接进入原四点手工对话框。历史已存标点不会被切换入口删除。
- 两模式共享整图/局部抓手H、左键自由平移、中键或Ctrl/空格平移、触控板pixelDelta水平平移；普通垂直滚轮仍缩放。点仍可拖动。单框双击直入；重叠处异步QMenu列出A/B/C…与取消，选中后进入对应牙位。
- T画框；与单个已有ROI对应时直接替换，与多个对应时选要替换的牙框，无对应时沿用新牙位录入。保留牙齿身份与原标点。Ctrl+Z/撤销框选恢复最近框，历史保存后可重开继续撤销；initial_auto_roi保留机器初始框。没有把撤销框选做成删除人工点。
- `app/main.py --annotation-mode manual|full`；类MainWindow默认full只为兼容原API/tests。`main_window.py`绑定病例与进度/取消/事务合并/保存，manual结果必须mode=segmentation且surfaces为空。
- `ai_client.py`通过QProcess调用独立 `app/ai_worker.py --mode full|segmentation`；开发态后端用相邻3.11 Python，安装态runtime/PanoDentalWorker.exe；GUI3.14不装Torch。
- 后端 `analyze_image(image_path, model_dir, output_dir, progress=None, cancelled=None, mode='full')`。首次分割boxes/contours/class/score与旧baseline完全一致。full把跨ROI候选归属实际牙齿、空间去重，缺失牙最多原向/180度/加宽原向三视图；阈值不变。output_dir必须不存在，raw mask/pose/变换完整落盘。
- `app/core/review_geometry.py`与后端boundary.py按原始闭合轮廓线段做连续最近点投影。保留raw_xy、pre_projection_xy、projected_xy及投影距离/线段/t/轮廓SHA，不把投影当人工复核。main_window对未人工改动旧候选同样可做轮廓校正；人工修改、复核或拒绝的点受保护。
- `ai_merge.py`一对一匹配牙框；手工大幅重画时仍用原分割bbox辅助匹配，避免重跑重复牙齿。模型cej→cej、bone_level→ac、apex→apex；cej2不得自动伪造。图像左右是image_side，不能擅自确认为解剖近远中。
- `models.py` schema5：Pt、Site.point_meta、Tooth.segmentation/candidate_surfaces/initial_auto_roi、CaseAnnotation.ai_runs/box_history。storage原子保存，迁移旧数据并拒绝未来schema。坐标保留浮点，四角动态导出；JSON roi_corners、CSV boxes.csv、Excel牙框坐标包括尚未打点的牙框。
- Qt生命周期修复7e9f881：PointItem信号连接QObject成员Slot，关联信息放annotation_ref，避免lambda强捕获view造成跨Python/Qt销毁后崩溃。拖动仅刷新文字/测量线，不能clear拖动中的Item；不要退回强捕获闭包。
- 移交完整项目文件夹时包含runs；单JSON坐标导出不是mask二进制项目包。

## 验收证据

- 后端 `reports/boundary_full_v1.local` / `boundary_segmentation_v1.local`、`boundary_validation.local.json`：full墙钟72.67秒/峰值1.4835GiB；纯分割墙钟16.81秒，31牙0点/0pose。以上是后端真实模型运行。
- UI `reports/boundary_ui_v12_final.local/report.json`：真实结果重放29断言，60显示点贴线、raw不丢、真实QTest拖点、保存重开、重画撤销、CSV/Excel/JSON及四角。它没有重复推理，不能称完整QProcess运行。
- `reports/v12-native/report.json`：实际冻结目录GUI→冻结QProcess纯分割12.74秒/1.484GiB，31牙0自动点；人工四点和拖点、抓手、重画/撤销、重叠框选择与正常保存退出，45产物断言。人工四点仅工程测试，未导入用户项目。
- 原core/smoke通过，新增AI/几何/模式/导航组合44 passed；随后测试销毁等待器去除pytest-qt警告，相关29项无警告通过。后端12项通过。无需无故重复昂贵推理。
- `reports/packaging-v1.2/verification-summary.json`：2535安装文件与实测目录bundle大小/SHA全匹配，四桌面/菜单快捷方式参数正确，安装版净PATH三入口分别默认manual1.92s/manual1.35s/full1.32s成功，Worker CPU NMS/ROIAlign/ORT/两权重SHA全部通过。
- 包 `dist/AI-integrated/牙槽骨吸收测量AI_安装包_v1.2.0-preview.exe`，446458634字节，SHA256 `9e606bb1d25723568ef37b1ee7a7f7ab2a60b79aa3060b1b271ca40103f3f6cc`。
- 安装目录 `C:/Users/Lenovo/AppData/Local/Programs/牙槽骨吸收测量AI`。原用户窗口已正常保存/关闭；原手工1.0与用户项目未移动删除。测试都在reports独立项目，最终last_project恢复真实用户项目，见settings-restored.json（before-native快照是更早QA遗留偏好，不要误恢复它）。没有构建/训练/推理后台进程。

## 环境、构建与后续

GUI `.venv/Scripts/python.exe -m app.main`，Python3.14.3/PySide6 6.11.2。后端相邻panodental/.venv为Python3.11.15/Torch2.6 CPU/torchvision0.21/ORT1.23.2。Ryzen7 6800H、16GB、AMD显卡，无CUDA，当前推理2线程。CPU环境重装用 `uv sync --locked --extra dev --extra cpu --extra weight-audit`，只uv sync会移除extras。

GUI测试用 `.venv/Scripts/python.exe -m pytest tests/test_ai_core.py tests/test_ai_ui.py tests/test_review_geometry.py tests/test_workflow_modes.py tests/test_canvas_navigation.py -q`，原测试单独运行 `python tests/test_core.py`、`python tests/test_smoke.py`。pytest8.4.2、pytest-qt4.5仅开发依赖，不进入安装包。

打包 `scripts/build_ai_windows.ps1` 的Worker/Gui/Assemble/Installer阶段；先定稿源码，再 `scripts/package_source.py --backend <相邻panodental目录>` 刷新随包SOURCE（本次97文件），再Assemble/Installer。必须保留净PATH、--clean与ICU排除，宿主poppler库会污染Qt；不要回用旧失败DLL/旧包。目标代码提交fc526dd、4383b03、40d6691、7e9f881、a5ba807；后端3d8f529，最终交接文档提交见git log。

尚未达成的医学目标：每牙三点齐全与CEJ/骨嵴顶独立准确率、跨医院/全景片域验证、完整原生PT对ONNX数值对照。后续训练应保存原片、独立mask/轮廓及人工真值，按患者划分训练/验证；只在原图画彩线再训不能保证小样本更准。用户当前优先无需重训的贴线与手工流程，相关工程调整已交付。Mac已取消。每轮继续更新STATUS/HANDOFF，不把尚未验证的医学效果记为完成。
