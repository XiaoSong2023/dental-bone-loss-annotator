# Windows 双模式内测版构建

已有纯手工 1.0 的 `build.spec`、`installer.iss` 与安装目录保持独立。
`1.2.0-preview` 使用已交付 AI 1.1 的 AppId 和目录原位升级，一个共享 exe 提供两个入口。

|桌面与开始菜单入口|启动参数|行为|
|---|---|---|
|牙槽骨吸收测量AI|`--annotation-mode full`|自动分割与三点候选，人工复核|
|牙槽骨吸收测量（分割人工版）|`--annotation-mode manual`|仅自动分割，四点由人工标注|

直接运行 exe 或安装后立即启动使用 `manual` 默认模式。两个入口共用 UI、运行库和模型文件。
分割人工版的实际推理不得调用 pose；该边界由应用/Worker 功能测试验证，启动参数自检不能代替它。

## 环境

- GUI：项目 `.venv`，Python 3.14.3，依赖 `requirements-ai-gui.txt`。
- Worker：Panodental 工程 `.venv`，Python 3.11.15，依赖 `requirements-ai-worker.txt`。
- Inno Setup 6：默认检查当前用户或 Program Files 下的标准安装目录。
- 两份真实模型：放入项目 `models` 下对应发布者目录；`models/README.md` 记录来源及限制。
- 随包说明/源码：`packaging/distribution` 的内容复制到应用安装目录顶层。

GUI 与 Worker 分别打包各自的 Python、NumPy 和动态库，避免两个 Python 版本或
Qt 与模型依赖在同一进程混用。已安装软件通过 QProcess 调用相邻 `runtime` 子目录内
的 `PanoDentalWorker.exe`，正常使用不需安装 Python 或 CUDA。

## 构建

在项目目录运行 PowerShell 7：

```powershell
./scripts/build_ai_windows.ps1 -WorkerProject 'D:\path\to\panodental'
```

`-Stage Gui`、`Worker`、`Assemble`、`Installer` 可依次分步执行。由于 GUI 构建会重新
生成应用目录，重建 GUI 之后须再次 Assemble 和 Installer。构建脚本不会安装、升级依赖，
也不会下载模型。请避开模型推理/训练期间构建，以控制本机内存使用。
构建会清空外部 Python 环境变量并将 PATH 限为 Windows 系统目录，避免开发工具
自带的 ICU/UCRT 等 DLL 混入安装包。Qt 6.11 使用 Windows 系统 ICU；
携带版本后缀符号的 poppler ICU 不能替代它。每次分析使用 `--clean`，
不会复用曾被外部 PATH 污染的依赖缓存。
Assemble 校验目标绝对路径与目录链接状态后完整替换应用内的 `runtime`，
防止单独重建 Worker 时残留上一次的 DLL。

输出为 `dist/AI-integrated/牙槽骨吸收测量AI_安装包_v1.2.0-preview.exe`，
带自包含 GUI、CPU Worker、两份模型、两个开始菜单/桌面入口和一个卸载程序。
分发整个安装包；单独复制目录内 GUI exe 会缺少运行库与模型。
升级安装不会自动关闭运行中的标注软件；应在确认用户已保存并自行退出后再更新被占用的文件。
构建或 Assemble 若发现进程正从目标产物目录运行，会报告进程名称和 PID 并停止覆盖，
不会终止这些进程。其他目录中运行的已安装软件不会因此阻塞独立构建。

`bundle-manifest.json` 记录每个安装资产的 SHA-256，`installer-sha256.json` 记录安装包校验值。

## 安装后验证

```powershell
./packaging/verify_frozen.ps1 -InstallDirectory 'D:\isolated-install' -ReportDirectory 'D:\test-reports'
./packaging/verify_shortcuts.ps1 -InstallDirectory 'D:\isolated-install' -ReportDirectory 'D:\test-reports'
```

该验证临时清空 Python 环境变量并将 PATH 缩减为 Windows 系统目录，从独立工作目录
依次调用 GUI 默认入口、显式 `manual` 和 `full` 入口的 `--selftest`，
要求报告包含实际采用的 `annotation_mode=manual/full`，再运行 Worker `--selftest --models`。
报告保存三种启动方式的 Qt 事件循环结果、Worker 真实运行时/模型校验结果、退出码与测试环境。
快捷方式检查另行确认两个桌面入口和两个开始菜单入口确实指向同一 exe，且模式参数正确。
它验证本机自包含运行；不等价于在另一台全新 Windows 机器上完成兼容性测试。

实际自动分割与标点必须另外用真实片子经安装版 Worker 完成并检查导出坐标，
启动自检本身不代表模型预测通过。内测版不冒称精度验证或正式发行签名已完成。
