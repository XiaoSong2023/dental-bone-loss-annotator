"""Archive explicit source folders only; never include images, weights or environments."""
from pathlib import Path
import argparse
import hashlib
import json
import zipfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = root / "packaging/distribution/SOURCE"
    out.mkdir(parents=True, exist_ok=True)
    members = []
    groups = [("manual-app", root, ["app", "tests", "scripts", "packaging"],
               ["requirements-ai-gui.txt", "requirements-ai-worker.txt", "installer_ai.iss", "README.md", "models/README.md"]),
              ("panodental-backend", args.backend, ["src", "tests", "scripts"],
               ["pyproject.toml", "uv.lock", "README.md"])]
    for prefix, base, dirs, files in groups:
        chosen = [base / item for item in files]
        for item in dirs:
            chosen.extend((base / item).rglob("*"))
        for path in chosen:
            if not path.is_file() or path.suffix.lower() not in {".py", ".md", ".txt", ".toml", ".lock", ".spec", ".ps1", ".iss"}:
                continue
            if "__pycache__" in path.parts or "distribution" in path.relative_to(base).parts:
                continue
            members.append((path, prefix + "/" + path.relative_to(base).as_posix()))
    archive = out / "integration-source.zip"
    manifest = []
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as packed:
        for path, name in sorted(members, key=lambda pair: pair[1]):
            content = path.read_bytes()
            packed.writestr(name, content)
            manifest.append({"path": name, "sha256": hashlib.sha256(content).hexdigest()})
    (out / "source-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{archive}: {len(manifest)} source files, {archive.stat().st_size} bytes")


if __name__ == "__main__":
    main()
