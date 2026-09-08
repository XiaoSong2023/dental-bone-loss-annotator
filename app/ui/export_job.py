"""Batch image rendering stays off the Qt UI thread."""

import os
from pathlib import Path
import shutil
import tempfile

from PySide6.QtCore import QThread, Signal

from ..core import export as exporter
from ..core.annotated_export import export_annotated_images
from ..core.project import Project


class ExportRecoveryError(OSError):
    """Leave backups in place if another process prevents rollback."""


def publish_files(paths: list[Path], destination: Path) -> list[Path]:
    """Publish a complete batch and roll back if Excel has locked a target."""
    backup = paths[0].parent / "previous"
    backup.mkdir()
    targets = [destination / source.name for source in paths]
    for target in targets:
        if target.exists():
            shutil.copy2(target, backup / target.name)
    replaced = []
    try:
        for source, target in zip(paths, targets):
            os.replace(source, target)
            replaced.append(target)
    except OSError as exc:
        failures = []
        for target in reversed(replaced):
            try:
                old = backup / target.name
                if old.exists():
                    os.replace(old, target)
                else:
                    target.unlink()
            except OSError as rollback_error:
                failures.append(str(rollback_error))
        if failures:
            raise ExportRecoveryError(
                f"导出被其他程序阻止，部分文件未能恢复。原文件备份保留在：{backup}\n"
                + "\n".join(failures)
            ) from exc
        raise OSError("导出未完成，原有导出文件已保留。请关闭占用文件的 Excel 或查看器后重试。\n"
                      + str(exc)) from exc
    return targets


class ExportJob(QThread):
    progress = Signal(int, int)

    def __init__(self, root, kind, adjust, entry_id=None, json_path=None, parent=None):
        super().__init__(parent)
        self.root, self.kind, self.adjust = root, kind, adjust
        self.entry_id, self.json_path = entry_id, json_path
        self.paths: list[Path] = []
        self.image_count = 0
        self.error = ""

    def run(self):
        stage = None
        try:
            # UI has saved its current edits and is locked until this job ends.
            project = Project.open(self.root)
            entries = None
            if self.kind == "json":
                entry = project.find(self.entry_id)
                if entry is None:
                    raise ValueError("当前病例已不在项目中，请重新打开项目后导出。")
                entries = [entry]
            image_dir = (self.json_path.parent if self.kind == "json"
                         else project.exports_dir)
            image_dir.mkdir(parents=True, exist_ok=True)
            stage = Path(tempfile.mkdtemp(prefix=".export-", dir=image_dir))
            archive, self.image_count = export_annotated_images(
                project, out_dir=stage, entries=entries, adjust=self.adjust,
                progress=self.progress.emit,
            )
            if self.kind == "csv":
                files = exporter.export_csv(project, project.grading, stage)
            elif self.kind == "excel":
                files = [exporter.export_excel(project, project.grading, stage / "汇总.xlsx")]
            else:
                files = [exporter.export_single_json(project, entry, stage / self.json_path.name)]
            self.paths = publish_files([*files, archive], image_dir)
        except ExportRecoveryError as exc:
            self.error = str(exc)
            stage = None  # Recovery folder must survive a failed rollback.
        except Exception as exc:
            self.error = str(exc) or type(exc).__name__
        finally:
            if stage is not None:
                shutil.rmtree(stage, ignore_errors=True)
