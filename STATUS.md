## 2026-09-08：1.4.0 已安装，带标注图片导出与旧项目保留完成

本节覆盖下方旧状态和删除旧病例授权。本轮用户要求所有已登记、标点、图片、已完成状态保留；之后希望在 Mac 继续开发，不是将 EXE 转为 DMG。

- CSV 导出同时产出 summary.csv、sites.csv、annotated_images.zip；Excel 与单例 JSON 同样附图片 ZIP，单例用独立名称，不覆盖整批包。ZIP 含 PNG 静态图、自包含 HTML 查看页、index、清单及说明。绘制实际当前框、轮廓、彩色点与编号，不取 raw/初始框或补造缺点；坐标表仍不导出矩形角。
- HTML 页内缩放保持标点/编号屏幕大小，PNG 是普通静态图片。真实浏览器按钮/滚轮测得41%→100%→196%→281%时标点直径恒为10px，48点映射误差<0.001px，实际拖动(-130,+80)对齐不变，console零错误/警告、零网络请求。CLI禁止file://，浏览器使用原样HTML的setContent进行实际渲染和交互，并非直接双击本地HTML；没有启动HTTP服务。
- 后台线程导出；整批图片和坐标暂存成功才发布，Excel锁文件时回滚，回滚也被阻止则保留恢复目录。7项UI导出/项目入口回归通过；真实Windows文件锁验证了summary锁定、sites锁定后的回滚、回滚失败时备份保留。
- 安装白名单只覆盖程序载荷，沿用AI AppId/目录。最早纯手工版共用快捷入口指向新版，旧目录与数据原地保留，不卸载/搬迁。显式“打开已有／旧版项目”发现原项目；空白启动不变。Project.create拒绝非空目录，Project.open不再把损坏/缺失索引变成空项目。19项旧schema/逻辑及物理done/原文件哈希保留测试通过，原core/smoke全通过。
- 名册复核确认本轮开始仍装1.3.0（1.3.1上轮未安装）。本次包含ea5dfe8修复，Excel/CSV×当前第1/2/3例6项回归通过；实际冻结GUI中的001从年龄性别空值导入为61/女，保存、导出、退出后仍保留。人口资料为工程夹具，不代表实际患者。
- 8项图片核心回归通过；导出/名册/现有工作流及逐牙组合34项通过，发布回滚加固后的相关UI7项再次通过。独立冻结GUI真实打开QA的已完成病例、导入Excel、点击CSV导出成功；31牙全部几何与68个当前点不变，CSV22行，PNG2440×1292；HTML坐标逐点精确匹配，原图SHA不变。证据 reports/release-v1.4/native-verification.json 及 native-*.png。
- 1.4.0-preview安装exit0。2,535安装文件与构建manifest逐项SHA/大小一致；原用户项目953文件逐项SHA/大小不变，共79片，19已完成。核验 reports/release-v1.4/installation-preservation.json。没有删除任何病例、用户图片、标注或旧手工版数据。
- 安装后净PATH空白启动自检1.53s；Worker两模型SHA、CPU NMS/ROIAlign/ORT健康全通过，训练0步。实际安装EXE已观察空白启动与关于1.4.0-preview。共享last_project已恢复实际用户项目，未遗留QA路径；唯一桌面/开始菜单入口核验通过。当前留有新版空白窗口供用户继续，无推理/构建任务。
- Windows安装包：dist/AI-integrated/牙槽骨吸收测量_安装包_v1.4.0-preview.exe，446568381字节，SHA256 8f289abd740daaa535e122493778a45c6910e54d32e5fb1f0ecda2fba5d8dc49。随包SOURCE含113源码文件。
- Mac接力：scripts/package_mac_handoff.py、docs/MAC_HANDOFF.md；交付路径 dist/Mac-handoff/PanoDental-Mac-Development-1.4.0-preview.zip。内容为gui/backend源码、依赖、两份固定SHA模型和许可；排除患者数据、Windows exe/DLL/runtime/.venv。Mac尚未构建、未产DMG，旧build_macos脚本仅人工版参考，AI worker路径和Mac依赖需在Mac适配验证。

以下均为历史记录，不得继续执行旧病例清理，也不要把1.3.1未安装状态当本轮结论。

## 2026-09-07：1.3.1 名册导入修复（已构建，尚未安装）

本节为最新状态；下方 1.3.0 安装及清理记录属于此前交付。

- 已复现：Excel 名册解析正常，但当前打开病例在导入后被 open_case 的隐式保存用旧 self.ann 空值覆盖。首张片默认打开 001，因此表现为首人年龄、性别缺失；切换到其他病例也会触发同一问题。
- 产品修复提交 ea5dfe8：import_roster 直接更新当前界面持有的同一份 annotation，随后刷新界面和病例列表，不重新打开当前病例。已有人工标点、备注和视图保留。
- 新增 Excel/CSV × 当前打开第 1/2/3 人共 6 项回归全部通过；涵盖重复导入、继续保存、切换病例、重开项目与手工点保留。另 35 项既有 UI/工作流/逐牙回归通过，原 core/smoke 脚本全部通过。测试资料是工程夹具，不是实际患者人口资料。
- 打包提交 404759d，版本 1.3.1-preview；GUI 与安装器已成功构建，沿用未改动的现有 CPU Worker/模型，SOURCE 包 106 个文件。安装包位于目标 GUI 工程 dist/AI-integrated/牙槽骨吸收测量_安装包_v1.3.1-preview.exe；installer-build.log 确认 Successful compile。
- 目录版原生检查已观察空白启动，并打开独立 QA 项目确认导入前首人资料为空。准备在文件对话框选择名册时，用户按物理 Esc 停止 Computer Use，已停止界面操作。尚未完成打包版名册导入验收，没有执行原位安装或安装后核验；当前安装仍为 1.3.0-preview。
- 证据集中在目标工程 reports/roster-fix-v1.3.1：roster-tests.xml、core-tests.log、smoke-tests.log、gui-build.log、installer-build.log、native-before.png。升级后重新导入一次原名册即可补齐已缺失资料。本轮未修改模型、未训练、未删除用户病例。

# STATUS — 2026-09-07

## 1.3 统一版交付完成

- 用户要求合并为一个版本；默认空白抓手，不自动恢复项目或运行模型。自动分割和自动标注为两个独立按钮。
- 分割只产牙框与完整轮廓；标注仅使用当前牙框快照，严格核对图像/快照SHA与全部牙ID、框、轮廓、牙位和来源，不重新分割、不新增或移动牙框。无轮廓手工框可识别真实候选但不造分割线。
- 原近中/远中各四点与四公式不变；应标点全齐或明确跳过后自动下一牙，拖点不跳，最后停留“完成标定”。
- CSV恢复summary/sites两个表、Excel恢复患者汇总/位点明细两表；JSON仅当前标注点及身份/计算结果，均不导出框四角、轮廓、raw/历史候选。完整项目内部几何和撤销记录仍保留。
- 77项组合回归、原core/smoke全部通过；历史真实模型结果经core载入UI后真实鼠标编辑、保存重开及仅点导出29项通过（reports/unified-ui-v13.local，不称新QProcess推理）。独立审查修复了raw边缘1e-4px容差契约。
- 独立keypoints真实运行：31牙身份/顺序/几何完全不变，23组69点覆盖15牙；0次分割、0次Torch导入，墙钟90.78秒/峰值0.791GiB。30牙保留轮廓，1牙仅移除轮廓验证无轮廓输入契约，非人工医学真值。后端28项通过，训练0步。
- 新GUI与Worker已冻结构建，源包105文件。真实原生双按钮、手工八点、拖点不跳步、完成一牙自动下一牙、保存与菜单三格式导出已通过。目录版实际QProcess得到31牙/0分割标点；随后单独识别、保留原31框/轮廓和8人工点，补入60候选点，最终68点、导出16牙22邻面行。`reports/unified-native-v13/verification.json`独立文件核验176项全部通过；UI操作与截图见同目录native-observations.json。没有训练，不把工程手工点当临床真值。
- 已安装1.3.0-preview，2,535安装文件与实测目录版逐项SHA/大小一致；净PATH默认建窗1.45秒、workflow=unified/startup=blank，Worker模型SHA/CPU算子/ORT健康通过。另以实际安装exe无参数启动观察空白抓手与两个按钮，正常AltF4退出，CIM无相关GUI/Worker进程；截图`reports/packaging-v1.3/installed-blank-start.png`。
- 唯一安装包`dist/AI-integrated/牙槽骨吸收测量_安装包_v1.3.0-preview.exe`，446,489,824字节；SHA256 `6095fdedd941403ccdb7abc57be2bede23c17d97efe9682cf3eb13c9f53fa802`。唯一桌面与开始菜单程序入口“牙槽骨吸收测量”，无mode参数；只剩1.3安装注册。SOURCE已提交5aef185。
- 已清除QSettings的last_project键，未恢复旧病例或QA项目路径；程序保留布局设置，正常启动仍空白。证据`reports/packaging-v1.3/settings-cleanup.json`。
- 用户明确允许旧病例清理：旧1.0官方卸载exit0；旧病例1031文件/268645342字节及7项多余旧安装包/构建产物已移入回收站，原位置均不存在。自动审批曾拒绝永久删除命令（仅返回blocked by policy，未给具体原因，未执行），故采用更安全可恢复清理，未永久擦除或清空回收站。保留原始开发附件、模型、源码、当前包与QA材料。证据`reports/packaging-v1.3/legacy-cases-recycled.json`、`obsolete-artifact-cleanup.json`、`verification-summary.json`。不能把下方1.2“旧病例保留”当本轮约束。

以下为1.2历史记录；其两入口、导出框角等行为由上述1.3需求覆盖。

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
