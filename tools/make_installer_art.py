#!/usr/bin/env python3
"""生成 Inno Setup 安装向导的品牌图片（BMP）。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
OUT = ROOT / "installer"
APP_ICON = ASSETS / "app_icon_256.png"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = (
        "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyh.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    )
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def gradient(w: int, h: int) -> Image.Image:
    img = Image.new("RGB", (w, h), "#100E1E")
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(1, h - 1)
        col = tuple(round(a + (b - a) * t) for a, b in
                    zip((16, 14, 30), (34, 23, 68)))
        d.line((0, y, w, y), fill=col)
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((-w * 0.6, h * 0.45, w * 1.2, h * 1.15),
               fill=(108, 75, 255, 150))
    gd.ellipse((w * 0.35, -h * 0.15, w * 1.6, h * 0.55),
               fill=(21, 201, 232, 90))
    glow = glow.filter(ImageFilter.GaussianBlur(26))
    img = Image.alpha_composite(img.convert("RGBA"), glow)
    # 细斜线装饰
    d = ImageDraw.Draw(img)
    for x in range(-h, w + h, 18):
        d.line((x, 0, x + h, h), fill=(255, 255, 255, 10), width=1)
    return img


def make_wizard() -> Image.Image:
    w, h = 164, 314
    img = gradient(w, h)
    icon = Image.open(APP_ICON).convert("RGBA").resize(
        (92, 92), Image.Resampling.LANCZOS)
    img.alpha_composite(icon, ((w - 92) // 2, 32))
    d = ImageDraw.Draw(img)
    f_title = font(17, bold=True)
    f_sub = font(12)
    f_small = font(9)
    d.text((w / 2, 140), "HSJ", font=f_title, fill="#FFFFFF", anchor="mm")
    d.text((w / 2, 160), "草稿转换器", font=f_sub, fill="#D9D3FF", anchor="mm")
    d.text((w / 2, 190), "PSD  /  ORA", font=f_small, fill="#8FE9F7",
           anchor="mm")
    d.line((24, 206, w - 24, 206), fill=(255, 255, 255, 44), width=1)
    d.text((w / 2, 222), "保留图层与混合模式", font=f_small,
           fill="#B9C2D8", anchor="mm")
    d.text((w / 2, 238), "本地离线转换", font=f_small,
           fill="#B9C2D8", anchor="mm")
    d.text((w / 2, h - 18), "v1.0.0", font=f_small,
           fill="#7E87A0", anchor="mm")
    return img.convert("RGB")


def make_small() -> Image.Image:
    size = 55
    img = Image.new("RGB", (size, size), "#17132B")
    icon = Image.open(APP_ICON).convert("RGBA").resize(
        (47, 47), Image.Resampling.LANCZOS)
    img.paste(icon, (4, 4), icon)
    return img


def make_header() -> Image.Image:
    w, h = 150, 57
    img = gradient(w, h)
    icon = Image.open(APP_ICON).convert("RGBA").resize(
        (38, 38), Image.Resampling.LANCZOS)
    img.alpha_composite(icon, (8, (h - 38) // 2))
    d = ImageDraw.Draw(img)
    d.text((52, 17), "HSJ 草稿转换器", font=font(11, bold=True),
           fill="#FFFFFF", anchor="lm")
    d.text((52, 35), "PSD / ORA · 本地离线", font=font(7),
           fill="#B9C2D8", anchor="lm")
    return img.convert("RGB")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    make_wizard().save(OUT / "wizard.bmp", format="BMP")
    make_small().save(OUT / "wizard_small.bmp", format="BMP")
    make_header().save(OUT / "header.bmp", format="BMP")
    print("安装向导图片已生成：", OUT)


if __name__ == "__main__":
    main()
