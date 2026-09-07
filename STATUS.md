# STATUS — 2026-09-07

## 1.2 本轮交付完成

- 同一源码两入口：`--annotation-mode manual`（默认，只分割、人工四点）和 `full`（分割、轮廓约束三点候选）。四点与四公式未变。
- 新增抓手、整图状态可平移、中键/触控板水平平移、单牙双击直入、重叠A/B/C选择、手工重画替换、Ctrl+Z持久撤销框选。
- schema5保存box_history、initial_auto_roi；点meta区分原始raw_xy/投影/人工当前坐标，候选几何投影不算人工复核。
- 后端3d8f529：真实灰度样片仍分割31牙；原17组三点/11牙，现23组69点/15牙，16牙缺完整三点。全点最大轮廓残差1.14e-13px；无训练、无阈值降低、无虚构补点。full墙钟72.67秒；纯分割16.81秒、pose执行0次。
- 最终UI真实结果重放：`reports/boundary_ui_v12_final.local/report.json`，29项通过；显示20组60点/15牙，原始23组保留；Qt鼠标拖点、保存重开、重画撤销、CSV/Excel/JSON与四角导出通过。此探针不重跑模型；全模型证据在相邻后端reports/boundary_validation.local.json。
- 核心4383b03、模式整合40d6691、UI7e9f881、打包fc526dd、说明a5ba807。组合测试发现的Qt原生退出已修复：PointItem信号闭包跨Python/Qt生命周期持有画布，改为QObject成员Slot并保留拖动中的Item；加入拖点→销毁→再次事件循环回归。44项AI/几何/工作流/导航组合回归通过，原core/smoke通过；测试等待器的警告随后清除，相关29项无警告通过。后端12项通过，独立代码审查无阻断项。
- 原生冻结目录版新模式实测：`reports/v12-native/report.json`，直接鼠标点击→QProcess→冻结Worker，31牙/0自动点/pose执行0次，内部12.74秒，峰值1.484GiB。单框双击直入FDI16、手动四点及根尖拖动、抓手平移、T替换牙框、Ctrl+Z恢复机器初始框并保点、重叠14/15的A/B/取消及选择A进入14均已操作通过。保存产物45项断言通过。人工点仅为工程交互测试，不能作医学真值。
- 已安装1.2.0-preview；桌面及开始菜单各有“牙槽骨吸收测量AI”（full）和“牙槽骨吸收测量（分割人工版）”（manual）。2,535个安装文件与实测目录版逐文件SHA/大小一致，0缺失/0差异。默认manual、显式manual、full在净PATH下分别1.92/1.35/1.32秒正常建窗退出；冻结Worker模型SHA、CPU算子及ORT健康全部通过。
- 安装包：`dist/AI-integrated/牙槽骨吸收测量AI_安装包_v1.2.0-preview.exe`，446,458,634字节；SHA256 `9e606bb1d25723568ef37b1ee7a7f7ab2a60b79aa3060b1b271ca40103f3f6cc`。集中证据：`reports/packaging-v1.2/verification-summary.json`。随包SOURCE包含97个集成源码文件，模型与依赖许可保留。
- 原用户窗口已正常保存确认无待存修改并正常关闭，未强杀。静默升级仅更新AI1.1目录，原手工1.0与其用户项目保留；QA在reports下独立项目进行，未改用户标注。最终last_project已恢复实际用户项目，证据settings-restored.json。所有构建、推理和测试进程均已结束。
- 训练解释与限制：docs/CONTOUR_REVIEW.md；使用说明已更新。后续正式医学准确率仍需独立专家真值，贴线不是解剖定位验证。

以下为1.1历史交付记录；其版本、schema与数量以以上1.2记录为准。

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
