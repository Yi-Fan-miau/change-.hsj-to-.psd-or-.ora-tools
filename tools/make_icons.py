#!/usr/bin/env python3
"""生成应用图标与界面图标（现代艺术风格）。

运行:
    python tools/make_icons.py

输出:
    assets/app_icon.ico            多尺寸 Windows 图标
    assets/app_icon_<size>.png     多尺寸 PNG
    assets/icons/*.png             界面装饰图标（透明背景）
"""

from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
ICONS = ASSETS / "icons"

S = 1024          # 最终图标尺寸
SS = 2            # 超采样倍数
M = S * SS        # 绘制画布尺寸


# ----------------------------------------------------------------- 基础工具
def _hex(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


def _stops(t: np.ndarray, colors: list[tuple[float, str]]) -> np.ndarray:
    """按停靠点插值，t 为 0..1 数组，返回 float RGB。"""
    positions = np.array([p for p, _ in colors], dtype=np.float64)
    palette = np.array([_hex(c) for _, c in colors], dtype=np.float64)
    out = np.empty(t.shape + (3,), dtype=np.float64)
    for ch in range(3):
        out[..., ch] = np.interp(t, positions, palette[:, ch])
    return out


def diagonal_gradient(size: int, colors: list[tuple[float, str]],
                      angle: float = 45.0) -> Image.Image:
    """生成带角度的线性渐变。"""
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float64)
    rad = math.radians(angle)
    t = (xx * math.cos(rad) + yy * math.sin(rad)) / (
        size * (abs(math.cos(rad)) + abs(math.sin(rad))))
    t = (t - t.min()) / max(1e-6, t.max() - t.min())
    rgb = _stops(t, colors)
    return Image.fromarray(rgb.astype(np.uint8), "RGB")


def rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size - 1, size - 1), radius=radius, fill=255)
    return mask


def card_layer(size: int, w: int, h: int, radius: int, angle: float,
               top: tuple[int, int, int, int], bottom: tuple[int, int, int, int],
               outline: tuple[int, int, int, int], outline_width: int) -> Image.Image:
    """绘制一张带渐变和描边的圆角玻璃卡片，并旋转。"""
    pad = int(max(w, h) * 0.25)
    canvas = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    card = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    grad = Image.new("RGBA", (w, h))
    gy, gx = np.mgrid[0:h, 0:w].astype(np.float64)
    t = np.clip((gx * 0.35 + gy * 0.65) / max(1, h - 1), 0, 1)[..., None]
    arr = (np.array(top, dtype=np.float64) * (1 - t)
           + np.array(bottom, dtype=np.float64) * t).astype(np.uint8)
    grad = Image.fromarray(arr, "RGBA")
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, w - 1, h - 1), radius=radius, fill=255)
    card = Image.composite(grad, Image.new("RGBA", (w, h), (0, 0, 0, 0)), mask)
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle(
        (outline_width // 2, outline_width // 2,
         w - 1 - outline_width // 2, h - 1 - outline_width // 2),
        radius=radius, outline=outline, width=outline_width)
    # 顶部高光，增加玻璃质感
    hi = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    hd = ImageDraw.Draw(hi)
    hd.rounded_rectangle((outline_width * 2, outline_width * 2,
                          w - outline_width * 2, int(h * 0.42)),
                         radius=radius, fill=(255, 255, 255, 34))
    hi = hi.filter(ImageFilter.GaussianBlur(outline_width * 2))
    card = Image.alpha_composite(card, Image.composite(
        hi, Image.new("RGBA", (w, h), (0, 0, 0, 0)), mask))
    card = card.rotate(angle, resample=Image.Resampling.BICUBIC, expand=False)
    canvas.alpha_composite(card, (pad, pad))
    return canvas


def blur_glow(layer: Image.Image, radius: int, alpha: float = 1.0) -> Image.Image:
    out = layer.filter(ImageFilter.GaussianBlur(radius))
    if alpha < 1.0:
        a = out.getchannel("A").point(lambda v: int(v * alpha))
        out.putalpha(a)
    return out


def sparkle(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
            color: tuple[int, int, int, int], thin: float = 0.26) -> None:
    """四角星芒。"""
    pts = [
        (cx, cy - r), (cx + r * thin, cy - r * thin),
        (cx + r, cy), (cx + r * thin, cy + r * thin),
        (cx, cy + r), (cx - r * thin, cy + r * thin),
        (cx - r, cy), (cx - r * thin, cy - r * thin),
    ]
    draw.polygon(pts, fill=color)


# ----------------------------------------------------------------- 应用图标
def make_app_icon() -> Image.Image:
    # 背景：极光渐变 + 柔光色块 + 斜向光带
    base = diagonal_gradient(M, [
        (0.00, "#151138"),
        (0.32, "#3B1E86"),
        (0.58, "#6D3DF2"),
        (0.82, "#1B9FE0"),
        (1.00, "#24E0CE"),
    ], angle=38).convert("RGBA")

    glow = Image.new("RGBA", (M, M), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((int(M * 0.52), int(M * 0.48), int(M * 1.15), int(M * 1.12)),
               fill=(255, 62, 148, 105))
    gd.ellipse((-int(M * 0.25), -int(M * 0.30), int(M * 0.45), int(M * 0.40)),
               fill=(46, 230, 255, 95))
    gd.ellipse((int(M * 0.55), -int(M * 0.25), int(M * 1.10), int(M * 0.30)),
               fill=(255, 196, 92, 55))
    glow = glow.filter(ImageFilter.GaussianBlur(int(M * 0.09)))
    base = Image.alpha_composite(base, glow)

    # 斜向半透明光带，增加现代艺术感
    band = Image.new("RGBA", (M, M), (0, 0, 0, 0))
    bd = ImageDraw.Draw(band)
    bd.polygon([(-M * 0.2, M * 0.72), (M * 0.80, -M * 0.25),
                (M * 1.02, -M * 0.02), (M * 0.02, M * 0.98)],
               fill=(255, 255, 255, 22))
    bd.polygon([(M * 0.35, M * 1.05), (M * 1.05, M * 0.15),
                (M * 1.05, M * 0.38), (M * 0.52, M * 1.05)],
               fill=(255, 255, 255, 13))
    base = Image.alpha_composite(base, band.filter(
        ImageFilter.GaussianBlur(int(M * 0.012))))

    # 细颗粒，避免大色块过于平滑
    rng = np.random.default_rng(20261017)
    noise = rng.normal(0, 3.2, (M, M, 1)).repeat(3, axis=2)
    base_arr = np.clip(np.asarray(base.convert("RGB"), dtype=np.float64)
                       + noise, 0, 255).astype(np.uint8)
    base = Image.fromarray(base_arr, "RGB").convert("RGBA")

    # 三层玻璃卡片（自后向前）
    cards = [
        dict(offset=(-150, -168), fill=(255, 255, 255, 34),
             outline=(255, 255, 255, 96), angle=-10),
        dict(offset=(-72, -82), fill=(255, 255, 255, 58),
             outline=(255, 255, 255, 130), angle=-3),
        dict(offset=(8, 6), fill=(255, 255, 255, 218),
             outline=(255, 255, 255, 245), angle=5),
    ]
    cw, chh, rad = int(M * 0.43), int(M * 0.43), int(M * 0.105)
    cx, cy = int(M * 0.50), int(M * 0.54)

    # 阴影
    shadow = Image.new("RGBA", (M, M), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    ox, oy = cards[-1]["offset"]
    sd.rounded_rectangle(
        (cx - cw // 2 + ox + int(M * 0.02), cy - chh // 2 + oy + int(M * 0.045),
         cx + cw // 2 + ox + int(M * 0.02), cy + chh // 2 + oy + int(M * 0.045)),
        radius=rad, fill=(14, 6, 42, 130))
    base = Image.alpha_composite(base, shadow.filter(
        ImageFilter.GaussianBlur(int(M * 0.035))))

    for idx, spec in enumerate(cards):
        if idx < 2:
            top, bottom = spec["fill"], (255, 255, 255, max(8, spec["fill"][3] // 3))
        else:
            top, bottom = (255, 255, 255, 248), (214, 228, 255, 224)
        layer = card_layer(M, cw, chh, rad, spec["angle"], top, bottom,
                           spec["outline"], max(6, int(M * 0.011)))
        ox, oy = spec["offset"]
        # card_layer 自带 25% 边距，计算粘贴位置
        pad = int(max(cw, chh) * 0.25)
        x = cx - cw // 2 + ox - pad
        y = cy - chh // 2 + oy - pad
        base.alpha_composite(layer, (max(0, x), max(0, y)))

    # 前卡片内部：渐变画笔弧线
    arc_pts = []
    for i in range(40):
        tt = i / 39
        ang = math.radians(-208 + 250 * tt)
        ax = cx + 34 - math.cos(ang) * M * 0.105
        ay = cy + 46 + math.sin(ang) * M * 0.105
        arc_pts.append((ax, ay))
    arc = diagonal_gradient(M, [
        (0.0, "#7C4DFF"), (0.5, "#EF4DA8"), (1.0, "#FFC15E")], angle=20)
    shape = Image.new("L", (M, M), 0)
    shd = ImageDraw.Draw(shape)
    shd.line(arc_pts, fill=255, width=int(M * 0.030), joint="curve")
    for p in (arc_pts[0], arc_pts[-1]):
        shd.ellipse((p[0] - M * 0.015, p[1] - M * 0.015,
                     p[0] + M * 0.015, p[1] + M * 0.015), fill=255)
    colored = Image.composite(arc.convert("RGBA"), Image.new(
        "RGBA", (M, M), (0, 0, 0, 0)), shape)
    base.alpha_composite(colored)

    # 星芒高光（前卡片右上角）
    sx, sy, sr = cx + cw * 0.36, cy - chh * 0.33, M * 0.075
    spark = Image.new("RGBA", (M, M), (0, 0, 0, 0))
    sparkle(ImageDraw.Draw(spark), sx, sy, sr, (255, 255, 255, 255))
    sparkle(ImageDraw.Draw(spark), sx - sr * 1.15, sy + sr * 0.95,
            sr * 0.30, (255, 214, 130, 235))
    sparkle(ImageDraw.Draw(spark), sx + sr * 1.05, sy + sr * 0.55,
            sr * 0.22, (126, 242, 255, 235))
    base.alpha_composite(blur_glow(spark, int(M * 0.018), 0.9))
    base.alpha_composite(spark)

    # 圆角遮罩 + 细描边
    mask = rounded_mask(M, int(M * 0.225))
    out = Image.new("RGBA", (M, M), (0, 0, 0, 0))
    out.paste(base, (0, 0), mask)
    edge = Image.new("RGBA", (M, M), (0, 0, 0, 0))
    ImageDraw.Draw(edge).rounded_rectangle(
        (2, 2, M - 3, M - 3), radius=int(M * 0.225),
        outline=(255, 255, 255, 46), width=max(2, int(M * 0.004)))
    out = Image.alpha_composite(out, Image.composite(
        edge, Image.new("RGBA", (M, M), (0, 0, 0, 0)), mask))
    return out.resize((S, S), Image.Resampling.LANCZOS)


# ----------------------------------------------------------------- 线性界面图标
def _draw_icon(size: int, color: str, painter) -> Image.Image:
    k = 4
    n = size * k
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    rgb = _hex(color) + (255,)
    width = max(2, int(n * 0.075))
    painter(d, n, rgb, width)
    return img.resize((size, size), Image.Resampling.LANCZOS)


def _line(d: ImageDraw.ImageDraw, pts: list[tuple[float, float]],
          color, width: int) -> None:
    d.line(pts, fill=color, width=width, joint="curve")
    r = width / 2
    for x, y in (pts[0], pts[-1]):
        d.ellipse((x - r, y - r, x + r, y + r), fill=color)


def paint_open(d, n, c, w):
    m = n * 0.14
    _line(d, [(m, n * 0.72), (m, n * 0.30), (n * 0.38, n * 0.30),
              (n * 0.47, n * 0.42), (n * 0.82, n * 0.42)], c, w)
    _line(d, [(m, n * 0.72), (n * 0.22, n * 0.52), (n * 0.90, n * 0.52),
              (n * 0.74, n * 0.82), (m, n * 0.82), (m, n * 0.72)], c, w)


def paint_folder(d, n, c, w):
    _line(d, [(n * 0.13, n * 0.78), (n * 0.13, n * 0.26), (n * 0.40, n * 0.26),
              (n * 0.50, n * 0.40), (n * 0.85, n * 0.40), (n * 0.85, n * 0.78),
              (n * 0.13, n * 0.78)], c, w)


def paint_layers(d, n, c, w):
    # 三个堆叠菱形
    for dy in (-0.26, 0.0, 0.26):
        pts = [(n * 0.5, n * (0.28 + dy)), (n * 0.86, n * (0.46 + dy)),
               (n * 0.5, n * (0.64 + dy)), (n * 0.14, n * (0.46 + dy))]
        _line(d, pts + [pts[0]], c, w)


def paint_convert(d, n, c, w):
    # 星芒 + 小星点
    sx, sy, r = n * 0.46, n * 0.44, n * 0.30
    pts = [(sx, sy - r), (sx + r * 0.20, sy - r * 0.20), (sx + r, sy),
           (sx + r * 0.20, sy + r * 0.20), (sx, sy + r),
           (sx - r * 0.20, sy + r * 0.20), (sx - r, sy),
           (sx - r * 0.20, sy - r * 0.20)]
    _line(d, pts + [pts[0]], c, max(2, int(w * 0.85)))
    for cx, cy, rr in ((n * 0.82, n * 0.20, n * 0.045),
                       (n * 0.16, n * 0.80, n * 0.035)):
        d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=c)


def paint_info(d, n, c, w):
    d.ellipse((n * 0.12, n * 0.12, n * 0.88, n * 0.88), outline=c, width=w)
    d.ellipse((n * 0.46, n * 0.29, n * 0.54, n * 0.37), fill=c)
    _line(d, [(n * 0.50, n * 0.46), (n * 0.50, n * 0.70)], c, w)


def paint_check(d, n, c, w):
    _line(d, [(n * 0.18, n * 0.53), (n * 0.42, n * 0.75), (n * 0.84, n * 0.27)],
          c, w)


def paint_clear(d, n, c, w):
    _line(d, [(n * 0.24, n * 0.30), (n * 0.76, n * 0.30)], c, w)
    _line(d, [(n * 0.34, n * 0.30), (n * 0.37, n * 0.80),
              (n * 0.63, n * 0.80), (n * 0.66, n * 0.30)], c, w)


def paint_copy(d, n, c, w):
    d.rounded_rectangle((n * 0.18, n * 0.18, n * 0.64, n * 0.72),
                        radius=n * 0.07, outline=c, width=w)
    d.rounded_rectangle((n * 0.36, n * 0.34, n * 0.82, n * 0.84),
                        radius=n * 0.07, outline=c, width=w)


def paint_about(d, n, c, w):
    paint_info(d, n, c, w)


def paint_close(d, n, c, w):
    _line(d, [(n * 0.24, n * 0.24), (n * 0.76, n * 0.76)], c, w)
    _line(d, [(n * 0.76, n * 0.24), (n * 0.24, n * 0.76)], c, w)


def paint_arrow(d, n, c, w):
    _line(d, [(n * 0.18, n * 0.50), (n * 0.78, n * 0.50)], c, w)
    _line(d, [(n * 0.58, n * 0.28), (n * 0.82, n * 0.50),
              (n * 0.58, n * 0.72)], c, w)


def make_logo_mark() -> Image.Image:
    """透明背景的白色图层标记，用于界面横幅。"""
    size = 512
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, (dx, dy, alpha) in enumerate(((52, 96, 72), (26, 48, 135), (0, 0, 255))):
        x0, y0 = 146 + dx, 146 + dy
        x1, y1 = x0 + 290, y0 + 290
        d.rounded_rectangle((x0, y0, x1, y1), radius=74,
                            outline=(255, 255, 255, alpha),
                            width=15 if i else 12)
    sx, sy, r = 390, 180, 92
    pts = [(sx, sy - r), (sx + r * 0.24, sy - r * 0.24), (sx + r, sy),
           (sx + r * 0.24, sy + r * 0.24), (sx, sy + r),
           (sx - r * 0.24, sy + r * 0.24), (sx - r, sy),
           (sx - r * 0.24, sy - r * 0.24)]
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    sparkle(ImageDraw.Draw(glow), sx, sy, r, (255, 255, 255, 190))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(18)))
    sparkle(d, sx, sy, r, (255, 255, 255, 255))
    sparkle(d, sx - r * 1.25, sy + r * 1.1, r * 0.28, (255, 214, 130, 235))
    return img


# ----------------------------------------------------------------- 入口
def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    ICONS.mkdir(parents=True, exist_ok=True)

    app = make_app_icon()
    sizes = [1024, 512, 256, 128, 64, 48, 40, 32, 24, 20, 16]
    for size in sizes:
        app.resize((size, size), Image.Resampling.LANCZOS).save(
            ASSETS / f"app_icon_{size}.png", optimize=True)
    app.save(ASSETS / "app_icon.ico", format="ICO",
             sizes=[(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)])

    logo = make_logo_mark()
    for size in (256, 128, 64):
        logo.resize((size, size), Image.Resampling.LANCZOS).save(
            ICONS / f"logo_mark_{size}.png", optimize=True)

    painters = {
        "open": paint_open,
        "folder": paint_folder,
        "layers": paint_layers,
        "convert": paint_convert,
        "info": paint_info,
        "check": paint_check,
        "clear": paint_clear,
        "copy": paint_copy,
        "about": paint_about,
        "close": paint_close,
        "arrow": paint_arrow,
    }
    for name, painter in painters.items():
        for size in (20, 24, 32, 48):
            for variant, color in (("light", "#E9EFFF"), ("muted", "#98A3BE"),
                                   ("accent", "#7DE8FF")):
                _draw_icon(size, color, painter).save(
                    ICONS / f"{name}_{variant}_{size}.png", optimize=True)

    print(f"图标已生成：{ASSETS}")


if __name__ == "__main__":
    main()
