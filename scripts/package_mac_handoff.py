"""Package local development sources and two verified models, never patient data.

This creates a transfer archive, not a macOS application. It does not download,
install, train, execute models, or invoke any existing platform build script.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile


VERSION = "1.4.0-preview"
SOURCE_SUFFIXES = {
    ".py", ".md", ".txt", ".toml", ".lock", ".spec", ".ps1", ".iss",
    ".sh", ".bat", ".yaml", ".yml", ".html", ".css", ".js", ".isl",
}
EXCLUDED = {
    "reports", "inputs", "images", "annotations", "exports", "runs", "models",
    ".git", ".venv", "venv", "build", "dist", "runtime", "__pycache__",
    ".pytest_cache", "node_modules", "distribution",
}
MODELS = {
    "chocodo--teeth-segmentation-odontoai/best.pth":
        "37bb200f5aa6620fc58fe549d8babd0080b6d2b661d1e33ec452ea3f329f7012",
    "rummanadib023--denpar-bone-loss-v2/surf_pose.onnx":
        "60d14e5b6560cbf834ffd0a6aff0c0558390224bbe1902199931479bfb89ad98",
}


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), *args], encoding="utf-8"
    ).strip()


def checked_file(root: Path, relative: str) -> Path:
    path = root / relative
    if not path.is_file() or not path.resolve().is_relative_to(root):
        raise ValueError(f"Missing file or path outside source root: {relative}")
    current = path
    while current != root:
        if current.is_symlink() or getattr(current, "is_junction", lambda: False)():
            raise ValueError(f"Linked files/directories are not packaged: {relative}")
        current = current.parent
    return path


def source_members(root: Path, prefix: str, directories: set[str]):
    # Use current working files, but only if explicitly tracked by Git. No .git history.
    paths = git(root, "ls-files", "-z").split("\0")
    for relative in paths:
        if not relative:
            continue
        parts = Path(relative).parts
        if any(part.lower() in EXCLUDED for part in parts):
            continue
        if len(parts) > 1 and parts[0] not in directories:
            continue
        if (Path(relative).suffix.lower() not in SOURCE_SUFFIXES
                and Path(relative).name not in {".gitignore", "LICENSE", "COPYING"}):
            continue
        path = checked_file(root, relative)
        if path.stat().st_size > 4 * 1024 * 1024:
            raise ValueError(f"Unexpectedly large source file: {relative}")
        yield f"{prefix}/{Path(relative).as_posix()}", path


def collect(gui: Path, backend: Path) -> dict[str, Path]:
    members = dict(source_members(gui, "gui", {"app", "tests", "scripts", "packaging", "docs", ".github"}))
    members.update(source_members(backend, "backend", {"src", "tests", "scripts", "packaging", "docs"}))
    # Explicit non-source assets; nothing is copied recursively from models/inputs.
    members["MAC_HANDOFF.md"] = checked_file(gui, "docs/MAC_HANDOFF.md")
    members["models/README.md"] = checked_file(gui, "models/README.md")
    members["gui/使用说明.md"] = checked_file(gui, "packaging/distribution/使用说明.md")
    for name in MODELS:
        members[f"models/{name}"] = checked_file(gui, f"models/{name}")
    for name in ("segmentation-model-card.md", "keypoint-model-card.md", "AGPL-3.0.txt"):
        members[f"THIRD_PARTY/models/{name}"] = checked_file(
            gui, f"packaging/distribution/THIRD_PARTY/models/{name}"
        )
    required = {
        "gui/app/main.py", "gui/app/ai_worker.py", "gui/app/ui/ai_client.py",
        "gui/requirements.txt", "gui/requirements-ai-gui.txt", "gui/requirements-ai-worker.txt",
        "gui/scripts/package_mac_handoff.py", "backend/pyproject.toml",
        "backend/src/panodental/inference.py", "gui/tests/test_roster_import_ui.py",
    }
    if missing := required - members.keys():
        raise ValueError(f"Required source files must be tracked before packaging: {sorted(missing)}")
    return dict(sorted(members.items()))


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="New .zip path; existing files are never replaced")
    parser.add_argument("--version", default=VERSION)
    parser.add_argument("--dry-run", action="store_true", help="Validate the manifest and model hashes without creating a ZIP")
    args = parser.parse_args()
    if not args.version or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for c in args.version):
        parser.error("--version must contain letters, numbers, dots or hyphens only")
    if not args.dry_run and args.output is None:
        parser.error("--output is required unless --dry-run is used")
    gui = Path(__file__).resolve().parents[1]
    backend = args.backend.resolve(strict=True)
    members = collect(gui, backend)
    records = []
    for name, path in members.items():
        actual = digest(path)
        expected = MODELS.get(name.removeprefix("models/")) if name.startswith("models/") else None
        if expected and actual != expected:
            raise ValueError(f"Trained model SHA-256 mismatch: {name}")
        records.append({"path": name, "bytes": path.stat().st_size, "sha256": actual})
    manifest = {
        "version": args.version,
        "artifact_type": "mac-development-handoff",
        "mac_built": False, "mac_verified": False, "patient_data_included": False,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "sources": {label: {"commit": git(root, "rev-parse", "HEAD"),
                             "working_tree_dirty": bool(git(root, "status", "--porcelain"))}
                    for label, root in (("gui", gui), ("backend", backend))},
        "files": records,
    }
    summary = {"version": args.version, "files": len(records),
               "uncompressed_bytes": sum(r["bytes"] for r in records),
               "models_sha256_verified": len(MODELS), "dry_run": args.dry_run}
    if args.dry_run:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    output = args.output.absolute()
    if output.suffix.lower() != ".zip":
        parser.error("--output must be a .zip file")
    temporary = output.with_name(output.name + ".partial")
    if output.exists() or temporary.exists():
        raise FileExistsError(f"Choose a new output path: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    prefix = f"PanoDental-Mac-Development-{args.version}"
    with zipfile.ZipFile(temporary, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for record in records:
            name = record["path"]
            copied_hash = hashlib.sha256()
            with members[name].open("rb") as source, archive.open(f"{prefix}/{name}", "w", force_zip64=True) as destination:
                while chunk := source.read(1024 * 1024):
                    destination.write(chunk)
                    copied_hash.update(chunk)
            if copied_hash.hexdigest() != record["sha256"]:
                raise RuntimeError(f"Source changed during packaging; partial archive retained: {name}")
        archive.writestr(f"{prefix}/MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(temporary) as archive:
        if broken := archive.testzip():
            raise RuntimeError(f"Archive CRC verification failed: {broken}")
    temporary.rename(output)
    summary.update({"output": str(output), "bytes": output.stat().st_size, "sha256": digest(output)})
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
