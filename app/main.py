"""程序入口。

    python -m app.main            正常启动
    python -m app.main --selftest 自检：启动 → 建窗 → 立即退出，打印耗时

打包后的 exe 同样支持 `--selftest`，用来在别人的机器上确认这份 exe 能跑
（不打开界面、不留任何文件）：

    牙槽骨吸收测量.exe --selftest
"""

from __future__ import annotations

import sys
import argparse
import time
from pathlib import Path

_T0 = time.monotonic()          # 越早越好：解释器一起来就开始计时

from PySide6.QtCore import QTimer            # noqa: E402
from PySide6.QtWidgets import QApplication   # noqa: E402

# 允许 `python app/main.py` 直接跑
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ui import theme                                          # noqa: E402
from app.ui.main_window import APP, APP_TITLE, ORG, MainWindow    # noqa: E402


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    selftest = "--selftest" in argv
    parser = argparse.ArgumentParser(add_help=False)
    # Accept old launcher arguments without exposing separate application modes.
    parser.add_argument("--annotation-mode", help=argparse.SUPPRESS)
    _options, qt_args = parser.parse_known_args([a for a in argv[1:] if a != "--selftest"])
    app = QApplication([argv[0], *qt_args])
    app.setOrganizationName(ORG)
    app.setApplicationName(APP)          # QSettings 键，保持稳定
    app.setApplicationDisplayName(APP_TITLE)
    theme.apply(app)

    win = MainWindow()
    win.show()

    if selftest:
        # 建完窗口就退。故意跑完一轮事件循环，确保 Qt 平台插件、字体、
        # 样式表都真的加载过 —— 只 import 成功不算数。
        def _done() -> None:
            _report(f"启动正常　耗时 {time.monotonic() - _T0:.2f}s"
                    f"　Qt 平台 {app.platformName()}"
                    f"　workflow=unified　startup={'blank' if win.project is None else 'loaded'}"
                    f"　窗口 {win.width()}×{win.height()}")
            app.quit()

        QTimer.singleShot(0, _done)

    return app.exec()


def _report(msg: str) -> None:
    """把自检结果送到所有可能有人看的地方。

    打包成窗口程序后 stdout 是无效句柄，`print` 等于扔进黑洞，
    所以同时写一份文件、并弹一个框 —— 自动化读文件，人看弹窗。
    """
    line = f"[selftest] OK  {msg}"
    try:
        print(line, flush=True)
    except OSError:
        pass

    import os
    out = os.environ.get("SELFTEST_OUT")
    if not out:
        base = Path(sys.executable if getattr(sys, "frozen", False) else __file__)
        out = str(base.with_name("selftest.log"))
    try:
        Path(out).write_text(line + "\n", encoding="utf-8")
    except OSError:
        pass

    if not os.environ.get("SELFTEST_QUIET"):
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(None, "自检通过", msg.replace("　", "\n"))


if __name__ == "__main__":
    raise SystemExit(main())
