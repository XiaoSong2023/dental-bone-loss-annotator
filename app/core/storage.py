"""标注文件的原子读写。

原子写（先写 .tmp 再 os.replace）是为了防止标到一半断电 / 崩溃时
把 70 张片子里的某一张写成半截 JSON。
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from .models import CaseAnnotation, SCHEMA_VERSION


def write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)           # 同盘 replace 是原子的
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def backup_dir(annotations_dir: Path) -> Path:
    return annotations_dir / "_backup"


def backup(path: Path) -> Path | None:
    """把当前的标注文件另存一份带时间戳的副本。"""
    if not path.exists():
        return None
    d = backup_dir(path.parent)
    d.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = d / f"{path.stem}-{stamp}.json"
    try:
        dst.write_bytes(path.read_bytes())
    except OSError:
        return None
    _prune_backups(d, path.stem, keep=20)
    return dst


def _prune_backups(d: Path, stem: str, keep: int) -> None:
    files = sorted(d.glob(f"{stem}-*.json"))
    for f in files[:-keep]:
        f.unlink(missing_ok=True)


def save_annotation(path: Path, ann: CaseAnnotation) -> None:
    """保存标注。

    ⚠️ 安全阀：如果这次要写的牙位数**比盘上已有的少**，先留一份带时间戳的备份。
       标注是手工一个点一个点标出来的，重标的代价极高；备份文件很小（几 KB），
       留 20 份也不占地方。任何一次意外清空都能从 annotations/_backup/ 找回。
    """
    prev = read_json(path)
    if prev is not None and len(prev.get("teeth", [])) > len(ann.teeth):
        backup(path)
    ann.touch()
    write_json_atomic(path, ann.to_dict())


def load_annotation(path: Path) -> CaseAnnotation | None:
    d = read_json(path)
    if d is None:
        return None
    return CaseAnnotation.from_dict(migrate(d))


def migrate(d: dict) -> dict:
    """把旧版 schema 升到当前版本。

    v1（根尖在 tooth 层共享）→ v2（每侧独立根尖）：
      把 tooth.apex 复制给两个 site 各一份，历史数据仍能打开，
      只是两侧共用同一个根尖坐标（可手动分开）。

    v2 → v3：v3 起每个位点可含 cej2（CEJ 下 2mm）。缺这个点的旧数据
      不需要任何转换 —— ①②公式照常算，③④公式会如实报「缺 P2」。

    注意 v1 里就有 cej2 字段，含义与 v3 完全一致（都是 CEJ 下 2mm），
    所以**必须原样保留**，不能像早期版本那样丢弃。
    """
    version = int(d.get("schema_version", 1))
    if version > SCHEMA_VERSION:
        raise ValueError("标注文件来自更新的软件版本，请更新软件后打开")
    if version < 2:
        for tooth in d.get("teeth", []):
            shared_apex = tooth.pop("apex", None)
            for site in tooth.get("sites", []):
                if shared_apex and not site.get("apex"):
                    site["apex"] = dict(shared_apex)
    d["schema_version"] = SCHEMA_VERSION
    return d


def file_sha1(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()
