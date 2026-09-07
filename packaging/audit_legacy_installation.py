"""Read-only legacy installation audit; never uninstalls or deletes user data.

The binary-log search is supporting evidence, not a parser for Inno's records.
The legacy source installer and its original bundle define the program payload.
Every installed file outside that payload and the exact uninstaller filenames is
identified as user data, including unknown files. Inventory is not authorization
to remove it; the separately recorded migration decision controls that scope.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import stat
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-directory", type=Path, required=True)
    parser.add_argument("--legacy-bundle", type=Path, required=True)
    parser.add_argument("--report-directory", type=Path, required=True)
    args = parser.parse_args()
    installed = args.install_directory.resolve(strict=True)
    legacy_bundle = args.legacy_bundle.resolve(strict=True)
    report = args.report_directory.resolve()
    if report == installed or installed in report.parents:
        raise ValueError("Audit reports must be outside the user installation/project.")
    items = [installed, *installed.rglob("*")]
    linked = [str(path) for path in items if path.lstat().st_file_attributes
              & stat.FILE_ATTRIBUTE_REPARSE_POINT]
    if linked:
        raise ValueError(f"Linked paths require separate review: {linked}")
    payload = {path.relative_to(legacy_bundle).as_posix()
               for path in legacy_bundle.rglob("*") if path.is_file()}
    payload_directories = {path.relative_to(legacy_bundle).as_posix()
                           for path in legacy_bundle.rglob("*") if path.is_dir()}
    if "project.json" in payload or any(path.startswith(("images/", "annotations/", "runs/"))
                                        for path in payload):
        raise ValueError("Legacy program bundle contains project data; do not infer deletions.")
    binary_log = (installed / "unins000.dat").read_bytes()
    program, user = [], []
    for path in sorted(items):
        if not path.is_file():
            continue
        relative = path.relative_to(installed).as_posix()
        entry = {"path": relative, "bytes": path.stat().st_size, "sha256": sha256(path),
                 "literal_path_present_in_uninstall_dat":
                     str(path).encode("utf-16le") in binary_log}
        if relative in payload or relative in {"unins000.dat", "unins000.exe"}:
            program.append(entry)
        else:
            user.append(entry)
    user_directories = [path.relative_to(installed).as_posix() for path in items
                        if path.is_dir() and path != installed
                        and path.relative_to(installed).as_posix() not in payload_directories]
    result = {
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "install_directory": str(installed), "legacy_bundle": str(legacy_bundle),
        "uninstall_log_header": binary_log[:64].split(b"\0", 1)[0].decode("ascii"),
        "binary_log_search_is_complete_parser": False,
        "program_files": program, "project_files": user,
        "project_directories": sorted(user_directories),
        "program_file_count": len(program), "project_file_count": len(user),
        "program_bytes": sum(item["bytes"] for item in program),
        "project_bytes": sum(item["bytes"] for item in user),
        "user_paths_found_in_binary_log": [item["path"] for item in user
                                          if item["literal_path_present_in_uninstall_dat"]],
        "safety_rule": "Inventory is not deletion authorization. Normal uninstall removes the "
                       "program; project deletion requires explicit authorization, a verified "
                       "replacement, and exact-path/process/link checks.",
    }
    report.mkdir(parents=True, exist_ok=True)
    (report / "legacy-audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
    for name, entries in (("legacy-program-files.txt", program), ("legacy-project-files.txt", user)):
        (report / name).write_text("\n".join(item["path"] for item in entries) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "program_file_count", "program_bytes", "project_file_count", "project_bytes",
        "user_paths_found_in_binary_log")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
