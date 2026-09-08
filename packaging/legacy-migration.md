# 更新安装与旧病例保留 — 2026-09-08

本轮用户明确要求所有已登记、已标注数据和图片原地保留，覆盖此前本机清理旧病例的授权。不得沿用旧清理流程，不执行旧卸载器，不删除、移动或重建任何用户项目。

统一版沿用 AI AppId {9D7D2163-EE63-4815-B2C1-37EE3B4E4B50}，UsePreviousAppDir=yes 在已有自动版上复用安装目录；只安装主程序、使用说明、_internal、runtime、models、SOURCE、THIRD_PARTY 白名单程序资产。安装源不含 project.json、images、annotations、exports、config 或 runs。
依据：[Inno安装目录复用](https://jrsoftware.org/ishelp/topic_setup_usepreviousappdir.htm)、[文件安装规则](https://jrsoftware.org/ishelp/topic_filessection.htm)。

纯手工 1.0 使用不同 AppId {8F3C1A62-4D77-4A5E-9B21-7C0E5A9D3F14}。
升级统一版覆盖同名桌面/开始菜单快捷入口，保留手工版程序和全部项目原位置，避免旧卸载器删除共享入口或误触项目。旧程序注册仍可能保留，这不是另外交付一份新版。安装器不终止用户正在运行的会话。安装前正常保存并关闭现有软件。

新版维持空白启动，通过“项目 → 打开已有／旧版项目”显式选择原项目。
发现逻辑只查共享 QSettings 的 last_project、当前程序目录、两种 AppId 的安装位置及两个默认安装根，不递归扫描或搬迁病例；其他自选项目可以正常“打开项目”。项目及标注兼容旧结构，保留原 patient、四点、ROI、done 状态和图片路径。images/done/ 的物理归档也原地保留。

新建只接受空目录。打开缺失、损坏或高版本 project.json 会报错，禁止生成空索引覆盖。单纯 Project.open 不创建目录或写盘；显式编辑保存才更新项目。工程测试见 tests/test_upgrade_preservation.py 和 tests/test_export_bundle_ui.py。

标注图片包使用SVG线条 non-scaling-stroke 和标点反向缩放的HTML查看器，而不是声称普通PNG支持固定屏幕尺寸；参考 [SVG vector-effect](https://developer.mozilla.org/en-US/docs/Web/SVG/Reference/Attribute/vector-effect)。导出在同目录暂存全部坐标文件和图片ZIP，生成成功才发布；目标被Excel占用时回滚已替换文件，避免新图配旧坐标。如回滚也被其他程序阻止，则保留备份并明确报告恢复目录。