#!/usr/bin/env python3
"""用 PyInstaller 构建 GUI（onedir）和 CLI（onefile）exe。

请在 Python 3.13 虚拟环境中运行：
    .venv-build\\Scripts\\python.exe packaging\\build_exe.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
APP_NAME = "HSJConverter"
VERSION = "1.0.0"


def _configure_tcl_env() -> None:
    """部分 Python 安装不会自动找到 Tcl/Tk 数据目录，构建时显式指定。"""
    if os.environ.get("TCL_LIBRARY") and os.environ.get("TK_LIBRARY"):
        return
    base = Path(getattr(sys, "base_prefix", sys.prefix)) / "tcl"
    if not base.is_dir():
        return
    tcl_dirs = sorted((p for p in base.glob("tcl[0-9]*") if p.is_dir()),
                      reverse=True)
    tk_dirs = sorted((p for p in base.glob("tk[0-9]*") if p.is_dir()),
                     reverse=True)
    if tcl_dirs:
        os.environ.setdefault("TCL_LIBRARY", str(tcl_dirs[0]))
    if tk_dirs:
        os.environ.setdefault("TK_LIBRARY", str(tk_dirs[0]))


def run(cmd: list[str]) -> None:
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> int:
    if not (ROOT / "assets" / "app_icon.ico").exists() or not (
            ROOT / "assets" / "icons").is_dir():
        print("生成图标资源 ...")
        subprocess.run([sys.executable, str(ROOT / "tools" / "make_icons.py")],
                       cwd=ROOT, check=True)
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("当前 Python 未安装 PyInstaller。请使用 .venv-build 中的 Python。")
        return 1

    t0 = time.time()
    py = sys.executable
    _configure_tcl_env()
    print(f"TCL_LIBRARY={os.environ.get('TCL_LIBRARY')}", flush=True)
    print(f"TK_LIBRARY={os.environ.get('TK_LIBRARY')}", flush=True)
    common = ["--noconfirm", "--clean", "--distpath", str(DIST)]

    run([py, "-m", "PyInstaller", *common,
         "--workpath", str(BUILD / "gui"),
         str(ROOT / "packaging" / "HSJConverter.spec")])
    run([py, "-m", "PyInstaller", *common,
         "--workpath", str(BUILD / "cli"),
         str(ROOT / "packaging" / "hsj2psd.spec")])

    app_dir = DIST / APP_NAME
    if not (app_dir / "HSJConverter.exe").exists():
        print("GUI 构建失败：找不到 dist/HSJConverter/HSJConverter.exe")
        return 1
    cli_exe = DIST / "hsj2psd.exe"
    if not cli_exe.exists():
        print("CLI 构建失败：找不到 dist/hsj2psd.exe")
        return 1

    shutil.copy2(cli_exe, app_dir / "hsj2psd.exe")
    shutil.copy2(ROOT / "README.md", app_dir / "README.md")

    # 便携版 zip
    portable = DIST / f"HSJConverter-{VERSION}-portable.zip"
    with zipfile.ZipFile(portable, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(app_dir.rglob("*")):
            if path.is_file():
                z.write(path, Path(APP_NAME) / path.relative_to(app_dir))

    print()
    print("构建完成：")
    print(f"  GUI:      {app_dir / 'HSJConverter.exe'}")
    print(f"  CLI:      {cli_exe}")
    print(f"  便携包:   {portable}  ({portable.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"  用时:     {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
