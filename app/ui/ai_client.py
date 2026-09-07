"""One disposable CPU worker per run; Qt never imports a model runtime."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal


def runtime_paths() -> tuple[list[str], Path, Path]:
    root = Path(__file__).resolve().parents[2]
    if getattr(sys, "frozen", False):
        root = Path(sys.executable).resolve().parent
        return [str(root / "runtime" / "PanoDentalWorker.exe")], root / "models", root
    source = root.parent / "0907牙周全景片分割及标注系统开发"
    python = source / "panodental" / ".venv" / "Scripts" / "python.exe"
    models = root / "models"
    if not models.is_dir():
        models = source / "inputs" / "community_models"
    return [str(python), "-m", "app.ai_worker"], models, root


class AiClient(QObject):
    progress = Signal(dict)
    completed = Signal(str)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self._read_stdout)
        self.process.readyReadStandardError.connect(self._read_stderr)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._error)
        self._buffer = b""
        self._result = None
        self._failure = ""
        self._cancelled = False
        self._active = False
        self._log_path = None
        self._output = None

    @property
    def busy(self) -> bool:
        return self._active

    def start(self, input_path: Path, output: Path, *, command=None,
              models=None, cwd=None) -> None:
        if self.busy:
            raise RuntimeError("已有自动标注正在运行")
        default_command, default_models, default_cwd = runtime_paths()
        command = command or default_command
        models, cwd = Path(models or default_models), Path(cwd or default_cwd)
        if not Path(command[0]).is_file():
            raise RuntimeError("未找到自动标注运行程序，请检查软件安装是否完整")
        if not models.is_dir():
            raise RuntimeError("未找到 models 模型文件夹，请检查软件安装是否完整")
        self._buffer, self._result, self._failure = b"", None, ""
        self._cancelled, self._active = False, True
        self._output = output.resolve()
        self._log_path = output.parent / "worker.log"
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUTF8", "1")
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("PYTHONPATH", str(cwd))
        self.process.setProcessEnvironment(env)
        self.process.setWorkingDirectory(str(cwd))
        args = [*command[1:], "--input", str(input_path), "--models", str(models),
                "--output", str(output)]
        self.process.start(command[0], args)

    def _log(self, data: bytes) -> None:
        if data and self._log_path:
            with self._log_path.open("ab") as stream:
                stream.write(data)

    def _read_stderr(self) -> None:
        self._log(bytes(self.process.readAllStandardError()))

    def _read_stdout(self) -> None:
        self._buffer += bytes(self.process.readAllStandardOutput())
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            self._line(line)

    def _line(self, line: bytes) -> None:
        if not line.strip():
            return
        self._log(line + b"\n")
        try:
            event = json.loads(line.decode("utf-8"))
        except (ValueError, UnicodeError):
            return
        if not isinstance(event, dict):
            return
        if event.get("type") == "progress":
            self.progress.emit(event)
        elif event.get("type") == "result":
            self._result = event.get("result_path")
        elif event.get("type") == "error":
            self._failure = str(event.get("message", "自动标注失败"))

    def _error(self, error) -> None:
        if error == QProcess.ProcessError.FailedToStart and self._active:
            self._active = False
            self.failed.emit("自动标注程序无法启动：" + self.process.errorString())

    def _finished(self, exit_code: int, exit_status) -> None:
        self._read_stdout()
        self._read_stderr()
        if self._buffer:
            self._line(self._buffer)
            self._buffer = b""
        if not self._active:
            return
        self._active = False
        if self._cancelled:
            self.cancelled.emit()
            return
        result = Path(self._result).resolve() if isinstance(self._result, str) else None
        if exit_code != 0 or exit_status != QProcess.ExitStatus.NormalExit or self._failure:
            self.failed.emit(self._failure or f"自动标注程序异常结束（退出码 {exit_code}）")
        elif result is None or not result.is_file() or not result.is_relative_to(self._output):
            self.failed.emit("自动标注未返回完整结果；现有标注未被更改")
        else:
            self.completed.emit(str(result))

    def cancel(self) -> None:
        if self.busy:
            self._cancelled = True
            self.process.terminate()
            QTimer.singleShot(1000, self, self._kill_cancelled)

    def _kill_cancelled(self) -> None:
        if self._cancelled and self.busy:
            self.process.kill()

    def stop(self) -> None:
        self.cancel()
        if self.process.state() != QProcess.ProcessState.NotRunning:
            if not self.process.waitForFinished(1200):
                self.process.kill()
                self.process.waitForFinished(1000)
