"""项目 —— 一批全景片的集合，管理导入、排序、状态与进度。

磁盘结构：
    <项目文件夹>/
    ├── project.json      项目元数据 + 病例状态索引
    ├── images/           原始全景片（默认复制进来，原文件夹不动）
    │   └── done/         仅当开启「物理归档」时才出现
    ├── annotations/      每张片一个 JSON
    ├── config/grading.json
    └── exports/

归档默认是**逻辑**的（状态写在 project.json），不动原图 ——
研究数据被物理移动后想回滚很麻烦。物理归档是设置里的可选开关。
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from . import storage
from .formula import DEFAULT_FORMULA_ID, FORMULAS
from .grading import GradingConfig
from .models import CaseAnnotation

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}

# ── 两种片型 ────────────────────────────────────────────────────────────
# 全景片：一张片 = 一个病人。
# 根尖片：一个**文件夹** = 一个病人，里面是这个病人的多张小牙片（全口可达 28 张）。
#         「全口最重位点」要跨该病人的所有片子取最大，导出也按病人汇总。
MODE_PANORAMIC = "panoramic"
MODE_PERIAPICAL = "periapical"
MODE_LABEL = {MODE_PANORAMIC: "全景片", MODE_PERIAPICAL: "根尖片（小牙片）"}

STATUS_PENDING = "pending"
STATUS_IN_PROGRESS = "in_progress"
STATUS_DONE = "done"
STATUS_FLAGGED = "flagged"

STATUS_LABEL = {
    STATUS_PENDING: "待标注",
    STATUS_IN_PROGRESS: "进行中",
    STATUS_DONE: "已完成",
    STATUS_FLAGGED: "已标记",
}

PROJECT_VERSION = 1


def natural_key(s: str):
    """自然排序：`2.jpg` 排在 `10.jpg` 前面，而不是字典序的反过来。"""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


@dataclass
class CaseEntry:
    """项目索引里的一条 —— 一张全景片。"""

    case_id: str                 # 项目内唯一的标识（通常来自文件名）
    image: str                   # 相对 images/ 的路径，如 "001.jpg"
    patient_key: str = ""        # 同一病人的片子共用一个 key；全景片下等于 case_id
    title: str = ""              # 列表里显示的名字，可重命名；空则用 case_id
    sha1: str = ""
    status: str = STATUS_PENDING
    order: int = 0
    annotated_teeth: int = 0     # 缓存，仅用于列表显示，真值在标注文件里
    updated: str = ""

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "image": self.image,
            "patient_key": self.patient_key,
            "title": self.title,
            "sha1": self.sha1,
            "status": self.status,
            "order": self.order,
            "annotated_teeth": self.annotated_teeth,
            "updated": self.updated,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CaseEntry":
        return cls(
            case_id=d["case_id"],
            image=d["image"],
            patient_key=d.get("patient_key") or d["case_id"],
            title=d.get("title", ""),
            sha1=d.get("sha1", ""),
            status=d.get("status", STATUS_PENDING),
            order=int(d.get("order", 0)),
            annotated_teeth=int(d.get("annotated_teeth", 0)),
            updated=d.get("updated", ""),
        )

    @property
    def display(self) -> str:
        return self.title or self.case_id


@dataclass
class ProjectSettings:
    physical_archive: bool = False    # 完成时把图片移到 images/done/
    copy_on_import: bool = True       # 导入时复制原图（否则只记录路径）
    mode: str = MODE_PANORAMIC        # 全景片 / 根尖片
    # 计算公式是**项目级**的，不是每张片各管各的 ——
    # 一批研究数据里一半用直线法一半用投影法会毁掉可比性。
    # 每个标注 JSON 仍会记下保存时用的公式 id，供追溯。
    formula_id: str = DEFAULT_FORMULA_ID
    def to_dict(self) -> dict:
        return {
            "physical_archive": self.physical_archive,
            "copy_on_import": self.copy_on_import,
            "formula_id": self.formula_id,
            "mode": self.mode,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ProjectSettings":
        base = cls()
        fid = str(d.get("formula_id", base.formula_id))
        mode = str(d.get("mode", base.mode))
        return cls(
            physical_archive=bool(d.get("physical_archive", base.physical_archive)),
            copy_on_import=bool(d.get("copy_on_import", base.copy_on_import)),
            formula_id=fid if fid in FORMULAS else base.formula_id,
            mode=mode if mode in MODE_LABEL else base.mode,
        )


class Project:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.name = self.root.name
        self.cases: list[CaseEntry] = []
        self.settings = ProjectSettings()
        self.grading = GradingConfig()
        self.created = ""

    # ── 路径 ─────────────────────────────────────────────────────
    @property
    def project_file(self) -> Path:
        return self.root / "project.json"

    @property
    def images_dir(self) -> Path:
        return self.root / "images"

    @property
    def annotations_dir(self) -> Path:
        return self.root / "annotations"

    @property
    def exports_dir(self) -> Path:
        return self.root / "exports"

    @property
    def grading_file(self) -> Path:
        return self.root / "config" / "grading.json"

    def image_path(self, entry: CaseEntry) -> Path:
        p = Path(entry.image)
        return p if p.is_absolute() else self.images_dir / p

    def annotation_path(self, entry: CaseEntry) -> Path:
        return self.annotations_dir / f"{entry.case_id}.json"

    # ── 生命周期 ──────────────────────────────────────────────────
    @classmethod
    def create(cls, root: Path) -> "Project":
        p = cls(root)
        if p.root.exists() and any(p.root.iterdir()):
            raise FileExistsError("所选文件夹不是空文件夹。已有病例请使用“打开项目”，以保留原有图片、标点和完成状态。")
        for d in (p.images_dir, p.annotations_dir, p.exports_dir, p.grading_file.parent):
            d.mkdir(parents=True, exist_ok=True)
        p.created = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        p.grading.save(p.grading_file)
        p.save()
        return p

    @classmethod
    def open(cls, root: Path) -> "Project":
        root = Path(root)
        p = cls(root)
        d = storage.read_json(p.project_file)
        if not isinstance(d, dict):
            raise ValueError("找不到可读取的 project.json；未创建或覆盖任何项目文件。请选择原项目文件夹。")
        try:
            version = int(d.get("version", 1))
        except (TypeError, ValueError) as exc:
            raise ValueError("项目版本信息损坏；原文件保持不变。") from exc
        if version > PROJECT_VERSION:
            raise ValueError("项目来自更新的软件版本，请更新软件后打开。")
        if not isinstance(d.get("cases"), list) or not isinstance(d.get("settings", {}), dict):
            raise ValueError("项目索引格式损坏；原文件保持不变。")
        p.name = d.get("name", root.name)
        p.created = d.get("created", "")
        try:
            p.settings = ProjectSettings.from_dict(d.get("settings", {}))
            p.cases = [CaseEntry.from_dict(c) for c in d["cases"]]
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ValueError("项目病例索引格式损坏；原文件保持不变。") from exc
        p.grading = GradingConfig.load(p.grading_file)
        return p

    def save(self) -> None:
        storage.write_json_atomic(
            self.project_file,
            {
                "version": PROJECT_VERSION,
                "name": self.name,
                "created": self.created,
                "settings": self.settings.to_dict(),
                "cases": [c.to_dict() for c in self.cases],
            },
        )

    def save_grading(self) -> None:
        self.grading.save(self.grading_file)

    # ── 导入 ─────────────────────────────────────────────────────
    def import_paths(self, paths: Iterable[Path]) -> tuple[list[CaseEntry], list[str]]:
        """导入图片或文件夹。返回 (新增的病例, 跳过的说明)。

        - 递归展开文件夹
        - 按文件名自然排序（1, 2, 10 而不是 1, 10, 2）
        - 用 sha1 去重：同一张片重复拖入不会产生两条
        - **根尖片模式下，图片所在的文件夹名 = 病人**。所以「一堆文件夹、每个
          文件夹里若干张根尖片」直接整体拖进来就行，会自动按病人分好组。
        """
        files: list[Path] = []
        for p in paths:
            p = Path(p)
            if p.is_dir():
                files.extend(
                    f for f in p.rglob("*")
                    if f.is_file() and f.suffix.lower() in IMAGE_SUFFIXES
                )
            elif p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES:
                files.append(p)

        periapical = self.settings.mode == MODE_PERIAPICAL
        files.sort(key=lambda f: (natural_key(f.parent.name) if periapical else [],
                                  natural_key(f.name)))

        known_sha = {c.sha1 for c in self.cases if c.sha1}
        known_ids = {c.case_id for c in self.cases}
        added: list[CaseEntry] = []
        skipped: list[str] = []
        next_order = max((c.order for c in self.cases), default=-1) + 1

        for src in files:
            try:
                sha = storage.file_sha1(src)
            except OSError as e:
                skipped.append(f"{src.name}：读取失败（{e}）")
                continue
            if sha in known_sha:
                skipped.append(f"{src.name}：内容重复，已跳过")
                continue

            folder = src.parent.name
            stem = f"{folder}_{src.stem}" if periapical and folder else src.stem
            case_id = self._unique_case_id(stem, known_ids)
            known_ids.add(case_id)

            if self.settings.copy_on_import:
                dst = self.images_dir / f"{case_id}{src.suffix.lower()}"
                self.images_dir.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(src, dst)
                except OSError as e:
                    skipped.append(f"{src.name}：复制失败（{e}）")
                    continue
                rel = dst.name
            else:
                rel = str(src.resolve())

            entry = CaseEntry(
                case_id=case_id,
                image=rel,
                patient_key=(folder or case_id) if periapical else case_id,
                title=src.stem if periapical else "",
                sha1=sha,
                order=next_order,
            )
            next_order += 1
            self.cases.append(entry)
            added.append(entry)
            known_sha.add(sha)

        if added:
            self.save()
        return added, skipped

    @staticmethod
    def _unique_case_id(stem: str, taken: set[str]) -> str:
        base = re.sub(r'[<>:"/\\|?*]', "_", stem).strip() or "case"
        if base not in taken:
            return base
        i = 2
        while f"{base}_{i}" in taken:
            i += 1
        return f"{base}_{i}"

    # ── 标注读写 ──────────────────────────────────────────────────
    def load_annotation(self, entry: CaseEntry) -> CaseAnnotation:
        ann = storage.load_annotation(self.annotation_path(entry))
        if ann is None:
            ann = CaseAnnotation(
                image_file=entry.image,
                image_sha1=entry.sha1,
                status=entry.status,
            )
            ann.patient.id = entry.case_id
        # 公式统一由项目设置决定，保证一批数据的可比性
        ann.formula_id = self.settings.formula_id
        return ann

    def save_annotation(self, entry: CaseEntry, ann: CaseAnnotation) -> None:
        ann.status = entry.status
        storage.save_annotation(self.annotation_path(entry), ann)
        entry.annotated_teeth = ann.annotated_tooth_count
        entry.updated = ann.updated
        self.save()

    # ── 状态 ─────────────────────────────────────────────────────
    def set_status(self, entry: CaseEntry, status: str) -> None:
        if entry.status == status:
            return
        old = entry.status
        entry.status = status
        if self.settings.physical_archive:
            self._apply_physical_archive(entry, old, status)
        self.save()

    def _apply_physical_archive(self, entry: CaseEntry, old: str, new: str) -> None:
        """可选的物理归档：完成时移到 images/done/，撤销时移回。

        失败时静默回退到逻辑归档 —— 绝不让文件操作阻断标注流程。
        """
        if Path(entry.image).is_absolute():
            return                       # 引用模式不动用户的原始文件
        done_dir = self.images_dir / "done"
        cur = self.images_dir / entry.image
        try:
            if new == STATUS_DONE and not entry.image.startswith("done/"):
                done_dir.mkdir(parents=True, exist_ok=True)
                dst = done_dir / Path(entry.image).name
                shutil.move(str(cur), str(dst))
                entry.image = f"done/{dst.name}"
            elif old == STATUS_DONE and entry.image.startswith("done/"):
                dst = self.images_dir / Path(entry.image).name
                shutil.move(str(cur), str(dst))
                entry.image = dst.name
        except OSError:
            pass

    # ── 查询 ─────────────────────────────────────────────────────
    def sorted_cases(self) -> list[CaseEntry]:
        return sorted(self.cases, key=lambda c: (c.order, natural_key(c.case_id)))

    def by_status(self, status: str) -> list[CaseEntry]:
        return [c for c in self.sorted_cases() if c.status == status]

    def counts(self) -> dict[str, int]:
        d = {k: 0 for k in STATUS_LABEL}
        for c in self.cases:
            d[c.status] = d.get(c.status, 0) + 1
        d["total"] = len(self.cases)
        d["remaining"] = d[STATUS_PENDING] + d[STATUS_IN_PROGRESS]
        return d

    @property
    def periapical(self) -> bool:
        return self.settings.mode == MODE_PERIAPICAL

    def patients(self) -> dict[str, list[CaseEntry]]:
        """病人 → 该病人的全部片子，按顺序。全景片模式下每个病人恰好一张。"""
        out: dict[str, list[CaseEntry]] = {}
        for c in self.sorted_cases():
            out.setdefault(c.patient_key or c.case_id, []).append(c)
        return out

    def siblings(self, entry: CaseEntry) -> list[CaseEntry]:
        """同一个病人的所有片子（含自己）。"""
        key = entry.patient_key or entry.case_id
        return [c for c in self.sorted_cases() if (c.patient_key or c.case_id) == key]

    def rename(self, entry: CaseEntry, title: str) -> None:
        entry.title = title.strip()
        self.save()

    def set_patient_key(self, entry: CaseEntry, key: str) -> None:
        entry.patient_key = key.strip() or entry.case_id
        self.save()

    def remove_case(self, entry: CaseEntry, delete_files: bool = False) -> None:
        """从项目移除一条病例。

        delete_files=True 时连同项目内的图片与标注一起删除；
        「引用模式」导入的原图**永远不删** —— 那是用户自己的原始数据。
        """
        if entry not in self.cases:
            return
        ann_path = self.annotation_path(entry)
        if delete_files:
            if not Path(entry.image).is_absolute():
                (self.images_dir / entry.image).unlink(missing_ok=True)
            ann_path.unlink(missing_ok=True)
        else:
            # 不删文件时，标注也保留 —— 万一是误删，重新导入就能接上
            pass
        self.cases.remove(entry)
        self.save()

    def find(self, case_id: str) -> Optional[CaseEntry]:
        return next((c for c in self.cases if c.case_id == case_id), None)

    def next_unfinished(self, after: Optional[CaseEntry] = None) -> Optional[CaseEntry]:
        """下一张未完成的片子。从 after 之后开始找，找不到就从头绕一圈。"""
        ordered = self.sorted_cases()
        if not ordered:
            return None
        start = 0
        if after is not None and after in ordered:
            start = ordered.index(after) + 1
        for c in ordered[start:] + ordered[:start]:
            if c.status in (STATUS_PENDING, STATUS_IN_PROGRESS) and c is not after:
                return c
        return None
