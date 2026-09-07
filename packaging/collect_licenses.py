"""Copy installed distribution notices without importing heavy libraries."""
import argparse
import json
import sys
from importlib.metadata import distribution, PackageNotFoundError
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("packages", nargs="+")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name in args.packages:
        try:
            dist = distribution(name)
        except PackageNotFoundError:
            continue
        notices = []
        for source in dist.files or []:
            basename = Path(str(source)).name.lower()
            in_license_directory = any(part.lower() in {"licenses", "licences"}
                                       for part in Path(str(source)).parts)
            if in_license_directory or basename.startswith(("license", "licence", "copying", "notice", "copyright")):
                full = Path(dist.locate_file(source))
                if not full.is_file():
                    continue
                relative = str(source).replace("..", "parent").replace("\\", "/")
                target = args.output / name / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(full.read_bytes())
                notices.append(target.relative_to(args.output).as_posix())
        manifest.append({"distribution": name, "version": dist.version,
                         "license_expression": dist.metadata.get("License-Expression"),
                         "license_metadata": dist.metadata.get("License"),
                         "homepage": dist.metadata.get("Home-page"),
                         "notice_files": notices})
    python_notices = []
    for name in ("LICENSE.txt", "LICENSE", "license.txt"):
        source = Path(sys.base_prefix) / name
        if source.is_file():
            target = args.output / "Python" / source.name
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(source.read_bytes())
            python_notices.append(target.relative_to(args.output).as_posix())
            break
    manifest.append({"distribution": "CPython", "version": sys.version.split()[0],
                     "license_expression": "Python-2.0",
                     "notice_files": python_notices})
    (args.output / "DEPENDENCIES.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
