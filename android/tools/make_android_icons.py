#!/usr/bin/env python3
"""Generate Android legacy/adaptive launcher icons from the desktop icon art."""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
ANDROID = ROOT / "android"
RES = ANDROID / "app" / "src" / "main" / "res"
APP_ICON = ROOT / "assets" / "app_icon_1024.png"
LOGO_MARK = ROOT / "assets" / "icons" / "logo_mark_256.png"

DENSITIES = {
    "mdpi": 48,
    "hdpi": 72,
    "xhdpi": 96,
    "xxhdpi": 144,
    "xxxhdpi": 192,
}


def gradient(size: int) -> Image.Image:
    img = Image.new("RGB", (size, size))
    d = ImageDraw.Draw(img)
    stops = [
        (0.00, (21, 17, 56)),
        (0.32, (59, 30, 134)),
        (0.58, (109, 61, 242)),
        (0.82, (27, 159, 224)),
        (1.00, (36, 224, 206)),
    ]
    for y in range(size):
        for_x_t = y / max(1, size - 1)
        # diagonal-ish gradient, computed per row
        row = []
        for x in range(size):
            t = (x * 0.45 + y * 0.55) / max(1, size - 1)
            for i in range(len(stops) - 1):
                t0, c0 = stops[i]
                t1, c1 = stops[i + 1]
                if t0 <= t <= t1:
                    k = (t - t0) / max(1e-6, t1 - t0)
                    row.append(tuple(round(a + (b - a) * k) for a, b in zip(c0, c1)))
                    break
            else:
                row.append(stops[-1][1])
        d.line((0, y, size, y), fill=row[0])
        for x in range(size):
            d.point((x, y), fill=row[x])
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((-size * 0.25, -size * 0.30, size * 0.55, size * 0.50),
               fill=(46, 230, 255, 90))
    gd.ellipse((size * 0.50, size * 0.45, size * 1.15, size * 1.12),
               fill=(255, 62, 148, 80))
    glow = glow.filter(ImageFilter.GaussianBlur(size * 0.10))
    img = Image.alpha_composite(img.convert("RGBA"), glow)
    return img


def adaptive_foreground() -> Image.Image:
    size = 432
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    mark = Image.open(LOGO_MARK).convert("RGBA").resize(
        (260, 260), Image.Resampling.LANCZOS)
    img.alpha_composite(mark, ((size - 260) // 2, (size - 260) // 2))
    return img


def ensure_source_assets() -> None:
    if APP_ICON.exists() and LOGO_MARK.exists():
        return
    script = ROOT / "tools" / "make_icons.py"
    if not script.exists():
        raise SystemExit("缺少桌面图标生成脚本 tools/make_icons.py")
    subprocess.run([sys.executable, str(script)], cwd=ROOT, check=True)


def main() -> None:
    ensure_source_assets()
    root_icon = Image.open(APP_ICON).convert("RGBA")
    for density, px in DENSITIES.items():
        folder = RES / f"mipmap-{density}"
        folder.mkdir(parents=True, exist_ok=True)
        resized = root_icon.resize((px, px), Image.Resampling.LANCZOS)
        resized.save(folder / "ic_launcher.png", optimize=True)
        resized.save(folder / "ic_launcher_round.png", optimize=True)

    drawable = RES / "drawable-nodpi"
    drawable.mkdir(parents=True, exist_ok=True)
    gradient(432).save(drawable / "ic_launcher_background.png", optimize=True)
    adaptive_foreground().save(drawable / "ic_launcher_foreground.png", optimize=True)
    root_icon.resize((128, 128), Image.Resampling.LANCZOS).save(
        drawable / "app_icon.png", optimize=True)
    print("Android icons generated at", RES)


if __name__ == "__main__":
    main()
