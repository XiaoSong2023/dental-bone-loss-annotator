# STATUS — 2026-09-07

当前：**Windows x64 首版已构建、安装并验证通过。** 在本用户已有手工软件 UI 内提供真实自动分割、CEJ／骨嵴交点／根尖候选、人工拖动、保存导出和框四角坐标。用户已取消 Mac。自动候选仍有漏检，不宣称每牙齐点或医学准确率达标。

## 已实现

- 保留原手工工作流，新增自动按钮、进度、取消；独立 CPU Worker，UI 不加载 Torch，不在主线程推理。
- 两份真实已训练社区权重，见 models/README.md。SHA 固定，strict tensor-only 载入分割；三点执行 ONNX。没有训练、没有随机/COCO/固定比例补点。
- 自动分割实例与 FDI 候选；上下文牙框裁剪，三点识别，768 letterbox 与 180°复查逆变换到原图。缺点留空。
- 自动结果按图像左右组显示，近远中需人工确认。CEJ-2mm 保持空缺，不能冒充第四个模型点。
- 人工调整保持模型 raw_xy 与历史；人工拒绝点在新一轮自动分析中不补回；已有手工点与框保留，大上下文框可按同 FDI 与几何关系匹配。
- schema 4，兼容旧标注迁移；模型运行完整结果位于项目 runs，点位来源与原始/当前坐标独立。坐标 JSON 保留完整浮点精度，禁止 NaN/Inf。
- 手绘与自动框动态导出四角：左上、右上、右下、左下。JSON roi_corners、CSV boxes.csv/位点表附列、Excel“牙框坐标”工作表；没有标点的框也导出。

## 真实证据与限制

审计工程 `../0907牙周全景片分割及标注系统开发/panodental/reports/full_inference_v3.local`：实际 JPG 全景片 2440×1292，31牙，17组三点/51点覆盖11牙；20牙没有完整三点。原生分割结构与参数数值对照：boxes/labels/scores/逐像素mask差均0；FrozenBatchNorm eps=0 已修正。全链路探针墙钟99.48秒（后端内部96.61秒）、峰值1.40GiB。

`reports/real_ui_probe_v2.local`：复用实际模型结果走现有UI，31牙、显示16组三点/48点，覆盖11牙，其余候选仍保存在完整原始结果。真实鼠标拖点→保存→重开→CSV/Excel/JSON，24条断言通过，四张截图。此探针没有重跑模型，人工拖点属于工程验证，不是医学复核；原样JPG快照及SHA匹配模型输入。

GUI分析输入是现有 loader 的未加看片增强的8位灰度PNG，与直接原始JPG输入可能产生不同模型结果；最终冻结版已按这个真实GUI输入路径完成验证，见下。旧loader不保留16bit强度，当前软件坐标基于其加载的影像尺寸；尚无DICOM/跨医院域验证。

训练步数0，已有训练权重足以运行首版功能；本机Ryzen7 6800H、15.19GiB RAM、AMD显卡、没有CUDA。未宣称每牙齐点或标注准确率。正式全景片域适配训练仍缺三点标注与验证集，当前低余量内存不宜启动长训，未租云GPU或改驱动。

## 工程验证

- 原有 `tests/test_core.py` 全部通过；原有 `tests/test_smoke.py` 全部通过（复核对话框事务语义断言已更新）。
- `tests/test_ai_core.py` 8项、`tests/test_ai_ui.py` 13项，在目标Python3.14/PySide6 6.11.2中合跑：21 passed in 4.47s。覆盖取消、拖动、拒绝点保护、大人工框匹配、输入SHA/空间拒绝、done状态复核回退、原始来源与四角导出。
- Worker 源码与冻结 exe `--selftest --models ...`：两个模型SHA、CPU NMS/ROIAlign、ORT输入输出结构通过，frozen=true、无需系统Python。

## 交付验证记录

- 安装包：`dist/AI-integrated/牙槽骨吸收测量AI_安装包_v1.1.0-ai-preview.exe`，446,413,344字节；SHA256 `f637c083a4d020ca4efdfd648644454f5af137ff27fa957be7e37cba551869e5`。
- 已正常安装：`C:/Users/Lenovo/AppData/Local/Programs/牙槽骨吸收测量AI/牙槽骨吸收测量AI.exe`；桌面“牙槽骨吸收测量AI”快捷方式已创建，原手工1.0版未覆盖。
- 目录版真实窗口点击自动按钮→QProcess→冻结Worker→UI自动保存→真实菜单CSV/Excel/JSON全部通过。`reports/installed-gui-e2e/report.json`：31牙、原始17组三点，GUI16组48点覆盖11牙，20牙缺完整三点；内部58.30秒、峰值1.48GiB；216项产物断言通过。输入PNG SHA与GUI来源记录一致；没有真值框、模拟预测或第四点补造。实际鼠标拖动与撤销复核独立见real_ui_probe_v2及UI回归。
- 安装版与上述实测目录版2535个资产SHA全部一致，0缺失/0差异。`reports/installed-manifest-verification.json`。
- 安装后清除PYTHONHOME/PYTHONPATH/VIRTUAL_ENV，PATH仅Windows系统目录、独立cwd：GUI1.97秒完成真实windows平台建窗，Worker frozen=true及两模型SHA/CPU算子/ORT均通过。`reports/frozen-installed-final/`、`reports/packaging-validation-summary.json`。
- 首次安装暴露QtCore错误，已定位并修复：构建PATH误采Codex/poppler的带后缀ICU符号库；净PATH加--clean重建，显式排除污染ICU，同时净构建Worker去掉非锁定UCRT来源。原失败测试安装已卸载，旧失败包SHA不得当成本次有效交付。Assemble会在验证范围内清理旧runtime，防止DLL残留。
- 随包含SOURCE集成源码与模型/依赖许可声明；本次没有上传病例或源码、没有云训练或后台长训。全部构建和推理子进程已结束。
