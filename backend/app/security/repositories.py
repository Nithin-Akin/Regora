"""Only read source: bounded extraction, no shell, no hooks, no symlink traversal."""

import os
import re
import shutil
import stat
import subprocess
import time
import zipfile
from pathlib import Path, PurePosixPath
from app.config import settings

IGNORED = {
    ".git",
    "node_modules",
    "venv",
    ".venv",
    "dist",
    "build",
    "coverage",
    "__pycache__",
    "vendor",
    ".idea",
    ".vscode",
    ".next",
    ".cache",
    ".mypy_cache",
    ".pytest_cache",
    "site-packages",
    "bower_components",
}
EXTENSIONS = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
}


def validate_github(url: str) -> str:
    if not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?/?", url):
        raise ValueError("Use a public repository URL: https://github.com/owner/repository")
    parts = url.rstrip("/").split("/")
    if any(p in {".", ".."} for p in parts[-2:]):
        raise ValueError("Invalid GitHub repository path")
    return url.rstrip("/")


def extract_zip(archive: Path, destination: Path):
    cfg = settings()
    if archive.stat().st_size > cfg.max_archive_mb * 1024**2:
        raise ValueError("Archive exceeds upload limit")
    total = 0
    try:
        with zipfile.ZipFile(archive) as z:
            entries = z.infolist()
            if len(entries) > cfg.max_files:
                raise ValueError("Archive contains too many files")
            for info in entries:
                p = PurePosixPath(info.filename)
                mode = info.external_attr >> 16
                if (
                    p.is_absolute()
                    or ".." in p.parts
                    or "\\" in info.filename
                    or ":" in info.filename
                    or stat.S_ISLNK(mode)
                ):
                    raise ValueError("Archive contains an unsafe path or symbolic link")
                total += info.file_size
                if info.file_size > cfg.max_file_bytes or total > cfg.max_extracted_mb * 1024**2:
                    raise ValueError("Archive exceeds extracted size limits")
                if any(part in IGNORED for part in p.parts) or info.is_dir():
                    continue
                out = destination.joinpath(*p.parts)
                out.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as src, out.open("wb") as dst:
                    shutil.copyfileobj(src, dst, length=65536)
    except zipfile.BadZipFile as e:
        raise ValueError("This file is not a valid ZIP archive") from e
    children = list(destination.iterdir())
    return children[0] if len(children) == 1 and children[0].is_dir() else destination


def clone_github(url: str, destination: Path):
    url = validate_github(url)
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
    command = [
        "git",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "protocol.file.allow=never",
        "-c",
        "http.followRedirects=false",
        "clone",
        "--depth",
        "1",
        "--single-branch",
        "--no-tags",
        "--",
        url,
        str(destination),
    ]
    started = time.monotonic()
    with open(os.devnull, "wb") as sink:
        process = subprocess.Popen(command, env=env, stdout=sink, stderr=sink)
        try:
            while process.poll() is None:
                size = 0
                count = 0
                for root, dirs, files in os.walk(destination, followlinks=False):
                    for name in files:
                        path = Path(root) / name
                        if not path.is_symlink():
                            size += path.stat().st_size
                            count += 1
                if (
                    size > settings().max_extracted_mb * 1024**2
                    or count > settings().max_files
                    or time.monotonic() - started > 120
                ):
                    raise ValueError("GitHub clone exceeded size, file count, or 120-second time limit")
                time.sleep(0.2)
            if process.returncode:
                raise ValueError("GitHub clone failed. Check that the repository is public and the URL exists.")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
    return destination


def scan_files(root: Path):
    files = []
    total = 0
    visited = 0
    for base, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in IGNORED and not (Path(base) / d).is_symlink())
        for name in sorted(names):
            path = Path(base) / name
            visited += 1
            if visited > settings().max_files:
                raise ValueError("Repository exceeds file count limit")
            if path.is_symlink():
                continue
            size = path.stat().st_size
            total += size
            if total > settings().max_extracted_mb * 1024**2:
                raise ValueError("Repository exceeds analysis size limit")
            if (
                path.suffix not in EXTENSIONS
                or size > settings().max_file_bytes
                or name.endswith((".min.js", ".d.ts", ".generated.ts", ".gen.ts"))
            ):
                continue
            raw = path.read_bytes()
            if b"\x00" in raw or any(len(line) > 2000 for line in raw.splitlines()):
                continue
            if any(marker in raw[:500].lower() for marker in (b"@generated", b"auto-generated", b"do not edit")):
                continue
            files.append(path)
    if not files:
        raise ValueError("No supported Python, JavaScript, or TypeScript source files were found")
    return files
