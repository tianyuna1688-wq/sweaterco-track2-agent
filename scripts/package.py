"""Build a portable source + built-frontend release, excluding secrets and runtime state."""

import hashlib
import json
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
output = root / "output"
output.mkdir(exist_ok=True)
archive = output / "SweaterCo-Track2-Platform-v1.0.0.zip"
roots = ["backend", "frontend", "data", "harness", "evals", "docs", "scripts"]
files = [
    root / name
    for name in [
        "README.md",
        "Dockerfile",
        "docker-compose.yml",
        ".dockerignore",
        ".gitignore",
        ".env.example",
        "启动平台.command",
    ]
]
ignored = {"node_modules", "__pycache__", ".pytest_cache", ".ruff_cache", "runtime"}
for folder in roots:
    for path in (root / folder).rglob("*"):
        if not path.is_file() or any(
            part in ignored for part in path.relative_to(root).parts
        ):
            continue
        if (
            path.name == ".DS_Store"
            or path.suffix in {".pyc", ".tsbuildinfo", ".sqlite3", ".db"}
            or (path.name.startswith(".env") and path.name != ".env.example")
        ):
            continue
        files.append(path)
manifest = {
    str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in sorted(files)
}
with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
    for path in sorted(files):
        z.write(path, "sweaterco-track2/" + str(path.relative_to(root)))
    z.writestr(
        "sweaterco-track2/release-manifest.json",
        json.dumps(
            {"version": "1.0.0", "sha256": manifest}, ensure_ascii=False, indent=2
        ),
    )
checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
(archive.with_suffix(".zip.sha256")).write_text(checksum + "  " + archive.name + "\n")
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert "sweaterco-track2/frontend/dist/index.html" in z.namelist()
print(
    json.dumps(
        {
            "archive": str(archive),
            "bytes": archive.stat().st_size,
            "files": len(files),
            "sha256": checksum,
        },
        indent=2,
    )
)
