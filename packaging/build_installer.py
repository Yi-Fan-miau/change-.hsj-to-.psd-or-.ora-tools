#!/usr/bin/env python3
"""用 NSIS 构建中文安装包。

首次运行会把 NSIS 便携版下载到 build/tools/（无需管理员权限）。
    .venv-build\\Scripts\\python.exe packaging\\build_installer.py
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
INSTALLER = ROOT / "installer"
OUTPUT = INSTALLER / "output"
DIST_APP = ROOT / "dist" / "HSJConverter" / "HSJConverter.exe"
NSIS_ZIP_URL = ("https://sourceforge.net/projects/nsis/files/"
                "NSIS%203/3.11/nsis-3.11.zip/download")


def _find_makensis() -> Path | None:
    matches = sorted((BUILD / "tools").rglob("makensis.exe"))
    for path in matches:
        if path.parent.name.lower() == "bin":
            return path
    return matches[0] if matches else None


def ensure_nsis() -> Path:
    path = _find_makensis()
    if path:
        return path
    tools = BUILD / "tools"
    tools.mkdir(parents=True, exist_ok=True)
    archive = tools / "nsis-3.11.zip"
    if not archive.exists():
        print("下载 NSIS 便携版 ...")
        req = urllib.request.Request(
            NSIS_ZIP_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=180) as resp, \
                open(archive, "wb") as fh:
            shutil.copyfileobj(resp, fh)
    print("解压 NSIS ...")
    with zipfile.ZipFile(archive) as z:
        z.extractall(tools)
    path = _find_makensis()
    if not path:
        raise SystemExit("NSIS 解压后找不到 makensis.exe")
    return path


def ensure_art() -> None:
    icon = ROOT / "assets" / "app_icon.ico"
    if not icon.exists() or not (ROOT / "assets" / "app_icon_256.png").exists():
        print("生成应用图标 ...")
        subprocess.run([sys.executable, str(ROOT / "tools" / "make_icons.py")],
                       cwd=ROOT, check=True)
    expected = [INSTALLER / "wizard.bmp", INSTALLER / "wizard_small.bmp",
                INSTALLER / "header.bmp"]
    if all(p.exists() for p in expected):
        return
    print("生成安装向导图片 ...")
    subprocess.run([sys.executable, str(ROOT / "tools" /
                                       "make_installer_art.py")],
                   cwd=ROOT, check=True)


def ensure_bom() -> None:
    script = INSTALLER / "HSJConverter.nsi"
    data = script.read_bytes()
    if not data.startswith(b"\xef\xbb\xbf"):
        script.write_bytes(b"\xef\xbb\xbf" + data)


def main() -> int:
    if not DIST_APP.exists():
        print("缺少 dist/HSJConverter/HSJConverter.exe，请先运行 "
              "packaging/build_exe.py")
        return 1
    ensure_art()
    ensure_bom()
    makensis = ensure_nsis()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    setup = OUTPUT / "HSJConverter-Setup-1.0.0.exe"
    if setup.exists():
        setup.unlink()
    t0 = time.time()
    subprocess.run([str(makensis), "/V2", "HSJConverter.nsi"],
                   cwd=INSTALLER, check=True)
    if not setup.exists():
        print("安装包构建失败：找不到输出文件")
        return 1
    digest = hashlib.sha256(setup.read_bytes()).hexdigest()
    print()
    print("安装包构建完成：")
    print(f"  {setup}  ({setup.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"  SHA256: {digest}")
    print(f"  用时: {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
