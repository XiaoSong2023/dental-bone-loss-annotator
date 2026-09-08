## 2026-09-08 最新接力：1.4.0 完成Windows更新，准备在Mac继续开发

用户最新要求：导出同时打包有框/轮廓/彩色当前点的影像；交互放大时点固定；所有旧项目和已完成状态保留（覆盖旧清理授权）；修复首人名册信息；本轮完成后转到Mac继续开发。EXE不能用作Mac源码，给源码+模型接力包。

目标工程 D:/Codex 项目集合/全景片标注加距离测量软件开发。产品提交：ea5dfe8名册修复、7b32d18安装/项目保护、8b40176图片核心、f64bd6d UI后台导出与发布回滚、3576c07打包文档、9ed4fef内置SOURCE；Mac脚本与说明69e6561。模型/后端推理代码未修改，训练0步。

- app/core/annotated_export.py: export_annotated_images(project,out_dir=None,entries=None,adjust=None,progress=None)->(Path,count)。默认全部病例，空/未完成也包含，缺点不补。entries指定时ZIP用selected哈希名避免单例覆盖整批。PNG是静态预览，HTML内SVG+反向缩放固定点/编号；禁止把PNG说成点不随图缩放。
- app/ui/export_job.py: 保存当前编辑后QThread读取项目，UI与自动保存暂停；所有输出先写同输出目录的.export-*，全部成功才publish_files。锁文件错误回滚，若回滚失败则ExportRecoveryError保留previous备份并告知目录，不得在finally删掉恢复材料。UIcloseEvent在导出期间拒绝退出避免销毁线程。
- 坐标表继续只summary/sites，不写框四角；JSON同样仅当前标点。图片ZIP可以展示完整几何。图像使用软件相同灰度加载与本次ImageAdjust，不改原片。当前标点/原始raw和历史仍在项目内部按原契约保存。
- installer_ai.iss沿用AI AppId/目录、UsePreviousAppDir=yes、仅程序资产白名单、CloseApplications=no。旧手工1.0不卸载，原目录与项目不搬迁；同名公共快捷方式覆盖为新版。不要执行旧卸载/清理文档的历史流程，packaging/legacy-migration.md已重写。
- project_discovery.discover_existing_projects(last_project)只读已知路径，显式打开；不自动恢复项目。create拒绝非空目录；open拒绝损坏/缺失/高版本project.json且不写盘。原schema1/2/3/5以及images/done物理归档兼容验证通过。
- 名册无需再改：本轮开始旧安装还1.3.0；已原位安装包含修复的1.4.0。现有001缺资料的用户项目只需重新导入原名册，不能替用户猜年龄性别。本次真实QA人口资料是工程夹具，不用于医学结论。

验收：图片核心8项、升级保留19项、名册6项、最终UI导出7项通过，组合34项和原core/smoke通过；真实Windows锁文件3种场景保留/回滚正确。原生冻结GUI真实导入和CSV+ZIP导出，31牙/68点/22CSV行，项目done和原图SHA保持，见reports/release-v1.4/native-verification.json。浏览器实际缩放41%至281%点直径恒10px，48点误差<0.001px，见reports/annotated-export-v1.3.2/browser-acceptance.json（目录名是工程报告历史命名，产品为1.4）。CLI拒绝file://后原样HTML通过setContent在真实浏览器渲染；不是直接双击文件验收。未跑新模型或训练。

已装1.4.0，2535程序资产匹配构建manifest；953用户项目文件SHA/大小全部保持，79片/19已完成。净PATHGUI1.53s、CPU Worker健康、唯一快捷方式验证通过。reports/release-v1.4/installed-version.png确认实际已安装版本。last_project已恢复用户实际项目，settings-restored.json可核验；新安装空白窗口留给用户，无待完成导出/推理。

Windows包 dist/AI-integrated/牙槽骨吸收测量_安装包_v1.4.0-preview.exe，SHA256 8f289abd740daaa535e122493778a45c6910e54d32e5fb1f0ecda2fba5d8dc49。
Mac传输包 dist/Mac-handoff/PanoDental-Mac-Development-1.4.0-preview.zip，使用已提交脚本从当前git跟踪源码白名单、固定两权重生成。包内MANIFEST含源提交与逐文件SHA；不包含患者或Windows运行库。以后在Mac解压，先读MAC_HANDOFF.md，建立新的GUI/backend环境，修正ai_client.runtime_paths与worker路径，再验证CPU链路并构建app/DMG。当前Mac未构建/未签名/未公证，不能声称复制EXE即可Mac运行；本轮不自动开始Mac开发。

下面旧状态保留为历史，最新数据保留与Mac接力要求优先。

## 2026-09-07 最新接力：1.3.1 修复已完成，原生验收被用户停止

当前任务是修复名册导入后当前病例（通常 001）年龄/性别被旧空值覆盖。目标工程为 D:/Codex 项目集合/全景片标注加距离测量软件开发；修复 ea5dfe8、打包 404759d。根因与已通过测试见最新 STATUS。不要重新研究 Excel 列识别、训练或修改模型。

1. 源码修复、新增 6 项回归、35 项已有回归及原 core/smoke 已通过。1.3.1 GUI、Assemble、Installer 均完成；安装器在 dist/AI-integrated/牙槽骨吸收测量_安装包_v1.3.1-preview.exe。CPU runtime 从已验证 1.3 目录复制复用，记录 reports/roster-fix-v1.3.1/runtime-reuse.json。
2. 用户在原生文件对话框输入 QA 名册路径之前/期间按物理 Esc 停止 Computer Use；本轮不得继续控制界面。不能报告原生导入通过或已安装 1.3.1。目录版 QA 进程最后 PID 60308，窗口 76025620，可能仍打开；不可假定其现时状态。此前旧安装空白窗口已正常关闭，没有强杀或丢弃待存病例。
3. 如用户继续，先重新观察现时窗口。独立 QA 项目 reports/roster-fix-v1.3.1/native-project，名册 reports/roster-fix-v1.3.1/名册回归测试.xlsx；测试病例 001_名册回归测试、年龄 61、女，人口资料为工程夹具。native-before.png 是实际导入前截图；尚无导入后原生验收证据。
4. 完成原生验收后正常关闭 QA，处理 QSettings last_project：之前值记录在 settings-before.json，本次打开 QA 可能已改变它；未恢复。统一启动仍保持空白，不自动打开该键。不得把 QA 项目设为用户默认项目。
5. 原位升级尚未进行：继续使用现有 AppId {9D7D2163-EE63-4815-B2C1-37EE3B4E4B50} 与 C:/Users/Lenovo/AppData/Local/Programs/牙槽骨吸收测量AI。安装后需验证安装文件、空白启动与唯一快捷入口，再清理已替代安装器/worker-build 构建暂存。当前 1.3.0 安装包及本轮 worker-build 暂存仍保留，没有新增病例清理。

以下为此前 1.3.0 及历史交付记录，不能将其已安装结论套用到 1.3.1。

# HANDOFF — 2026-09-07

## 当前状态

1.3.0-preview统一版已交付，产品代码已定稿、测试与目录原生双按钮验收通过，已安装并清理多余版本；最终证据见本文件末尾及STATUS。不要重做开发规划或重新询问Mac、权重、是否可清理旧病例。

用户最新要求优先于1.2：只保留一个软件；空白抓手启动，不自动打开项目；自动分割与自动标注分别主动点击；原四点/四公式、逐牙手工标定、保存导出；导出不含矩形四角。用户已另行明确允许旧版病例清理。

## 关键契约

- GUI `app/main.py`唯一入口，不以manual/full区分软件；历史annotation-mode参数仅兼容忽略。selftest输出workflow=unified、startup=blank。MainWindow不调度_restore_last_project，QSettings只恢复窗口/面板布局。
- `main_window.py`的start_auto_segmentation只运行segmentation，start_auto_annotation只运行keypoints；无牙框时后者禁用。两个按钮不串联、不自动触发。UI主线程不加载模型。
- `ai_client.py`/`ai_worker.py`传递 `--mode segmentation|keypoints` 与keypoints所需 `--teeth <snapshot>`。后端CLI保留full用于旧数据对照，但GUI没有合并执行入口。
- teeth.json：schema_version=1，image的width/height/sha256，teeth数组的source_tooth_id=instance_id=UI tooth_id、fdi、origin、现有seg.score或null、当前bbox_xyxy、现有contours或空。UI保存原灰度PNG与快照SHA；完成时同时核对PNG、快照字节、后端teeth_source.sha256与当前选牙集合。每颗输入牙必须在输出中保留，即便surfaces为空。
- 后端 `analyze_image(..., mode='keypoints', teeth_path=...)`只加载pose/ORT，不校验或加载分割权重，不导入Torch。snapshot校验后，只把轮廓或人工矩形栅格用作内部候选归属。人工框的矩形不是牙齿轮廓，不能输出假mask/score。models.segmentation=null、segmentation.forward_count=0。
- `ai_merge.py`keypoints按精确source_tooth_id合并并核对全部原框/轮廓/牙位/来源/score；只填点，不做IoU配牙、不新增牙或改segmentation/initial_auto_roi。segmentation结果含surfaces会拒绝。原手工/复核/拒绝点保护不变。
- 后端raw_xy保留原回映数值，允许解码契约的1e-4px边缘舍入；当前显示xy仍必须在原图范围。此兼容由726455d修复并回归验证。
- 有轮廓的候选精确投影至最近闭合线段，原值/校正值/投影距离各存；无轮廓点projected_xy与boundary_projection为null，xy/raw保持模型预测。不降低阈值、不编造缺点、不把贴线等同于医学准确。
- 近中/远中各cej、cej2、ac、apex四点、四公式不变。ToothDialog填点/明确跳过后扫描本牙所有空位；未齐不跳下一牙，补齐自动下一牙，最后停留完成标定。拖动不跳牙，撤销能回到被编辑牙。
- 抓手H、T手工框、中键/触控板平移、重叠牙框A/B选择、框替换与持久Ctrl+Z撤销保留。Qt PointItem必须继续用QObject成员Slot，不能恢复强捕获view闭包导致销毁后崩溃。
- 项目内部schema5仍保存完整geometry、raw和history；用户CSV只summary.csv/sites.csv，Excel只患者汇总/位点明细，JSON只当前位点、身份及派生结果，无roi/roi_corners/segmentation/candidate_surfaces/point_meta/ai_runs/box_history/骨曲线。未标点牙不导出；原有公式列保留。识别出的旧版boxes.csv会在重导CSV时清理，其他自有文件不动。

## 验证与环境

目标GUI `.venv`：Python3.14.3/PySide6 6.11.2。相邻panodental后端 `.venv`：Python3.11.15/Torch2.6 CPU/torchvision0.21/ORT1.23.2。CPU2线程，无训练、无CUDA依赖、无上传/云GPU。

77项组合回归：test_ai_core、test_ai_ui、test_review_geometry、test_workflow_modes、test_canvas_navigation、test_keypoint_merge、test_ai_keypoints_protocol、test_tooth_progression；原test_core/test_smoke全部通过。后端28项通过。

`reports/unified-ui-v13.local/report.json`为历史真实full结果经core载入→UI真实鼠标编辑/保存重开/仅点导出29断言。该脚本不模拟新的UI操作完成、不重跑模型，不能称QProcess推理。

`reports/unified-native-v13/native-observations.json`记录最终冻结目录GUI真实操作：空白抓手启动，载入影像不推理，分割按钮得到31牙框/轮廓0点；双击FDI16手工近远中八点，拖动不跳步，完成本牙自动从23/31至24/31，点击完成标定。随后单独标注按钮启动冻结Worker的keypoints模式，保留全部原框/轮廓/identity和8人工点，补60候选点。实际菜单导出CSV/Excel/JSON、正常关闭。`verification.json`由只读verify_native.py作176项全通过核验，最终68点、16导出牙、22邻面行；CSV仅2文件、Excel2表、JSON无几何/raw/meta且当前坐标精确匹配。测试项目独立于待删除旧病例；手工点只验证交互，不作解剖真值。

后端 `reports/keypoints_only_v1.report.json`为一次真实keypoints模型运行；31牙输入身份/几何不变，23组三点69点覆盖15牙，0seg/0Torch，90.78秒/0.791GiB。30牙有轮廓，FDI36仅去轮廓作为契约工程测试，真实2组6点未约束，不是专家真值。正式全景片医学准确率/每牙齐点仍未保证。

## 打包与清理

1.3唯一桌面/StartMenu程序入口“牙槽骨吸收测量”，不传mode。安装仍用AI AppId和 `C:/Users/Lenovo/AppData/Local/Programs/牙槽骨吸收测量AI`，内部exe旧名不代表另一版本。包名 `dist/AI-integrated/牙槽骨吸收测量_安装包_v1.3.0-preview.exe`。

净PATH/--clean/ICU排除必须保留；先定稿→build Worker/Gui→刷新SOURCE→Assemble/health→Installer。SOURCE本轮105源码文件，不含病例、reports、inputs或backups。初始打包b2f38a8、迁移授权1597d3a，后端bf11933、Worker/client8bf80f2、export adfda97、core39c20b4/726455d、UI867f4c5、说明与probe d4b9d26。

清理授权与实情：用户允许清理旧病例；旧1.0官方卸载exit0，新1.3安装验证后，精确旧目录 `C:/Users/Lenovo/AppData/Local/Programs/牙槽骨吸收测量`（1031病例文件268645342bytes）已移入回收站，原路径不存在，带AI后缀的新安装目录保留。永久删除命令被自动审批在执行前拒绝，仅返回blocked by policy未给具体原因；未重试永久删除，改为系统明确SendToRecycleBin的可恢复方式并成功。7项审计过的旧dist安装器/独立程序/构建目录也已回收，旧mode快捷方式已清理。没有清空回收站；不是永久擦除。原始附件、模型、源码、当前包与QA材料保留。不要把早先1.2“恢复last_project/保留1.0病例”的记录当现行要求。

## 最终交付记录

- 1.3.0-preview已安装到上述AI路径；2,535安装资产逐项SHA/大小一致、0缺失0差异。桌面及开始菜单各一个“牙槽骨吸收测量”程序入口，参数为空，注册仅1.3。
- 最终安装包446,489,824字节，SHA256 `6095fdedd941403ccdb7abc57be2bede23c17d97efe9682cf3eb13c9f53fa802`；源码包105文件，SHA256 `87211c974018d1b6b0fcce7aed148175bcbaf17a5e6dd9959e4523af01ed86d4`，提交5aef185。
- 安装后净PATH默认自检1.45秒，workflow=unified/startup=blank；冻结CPU Worker的两模型SHA、NMS、ROIAlign、ORT全部通过。父端另用实际已安装exe无参数启动（PID52368）观察空白抓手、空病例列表、两个按钮，再正常AltF4退出；CIM无GUI/Worker。
- `reports/packaging-v1.3/verification-summary.json`汇总包、安装、健康与清理证据；`installed-blank-start.png`是最终实际窗口；`legacy-cases-recycled.json`、`obsolete-artifact-cleanup.json`记录可恢复清理，均不等于永久删除。
- `settings-cleanup.json`确认QSettings PerioTools/全景片牙槽骨吸收测量的last_project已清除，未恢复旧病例或QA路径；其他布局设置保留。
- 目录真实原生验收见上一节native-observations及176项verification。以后从唯一1.3继续迭代，保持两按钮与仅点导出契约；每轮更新STATUS/HANDOFF。
