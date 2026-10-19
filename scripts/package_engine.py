"""Build a reduced, version-pinned source payload for first-run uv sync.

Runs on GitHub Actions after compiling sub2gen's frontend and Chrome extension.
No sub2gen source is downloaded by the end user.
"""
from pathlib import Path
import zipfile

source = Path("upstream-sub2gen")
dest = Path("engine-payload")
dest.mkdir(exist_ok=True)
archive = dest / "sub2gen.zip"
excluded_names = {".git", ".venv", "node_modules", "__pycache__", ".runtime", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
excluded_parts = {"tests", "test", "docs", ".github"}
allowed = {
    "pyproject.toml", "uv.lock", ".python-version", "README.md", "LICENSE",
    "config", "apps", "packages", "vendor", "scripts", "infra", "package.json"
}
with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as target:
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(source)
        if rel.parts[0] not in allowed:
            continue
        if any(segment in excluded_names or segment in excluded_parts for segment in rel.parts):
            continue
        # Include compiled UI and extension, but not intermediate outputs.
        if "dist" in rel.parts and "captcha-extension" not in rel.parts:
            continue
        target.write(path, rel.as_posix())
with zipfile.ZipFile(archive) as bundle:
    required = {
        "pyproject.toml", "uv.lock", "apps/api/static/index.html",
        "apps/captcha-extension/dist/manifest.json",
        "config/setting_example.toml",
    }
    absent = required - set(bundle.namelist())
    if absent:
        raise SystemExit("Incomplete sub2gen payload: " + ", ".join(sorted(absent)))
print(f"Created {archive} ({archive.stat().st_size / 1048576:.1f} MiB)")
