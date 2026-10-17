"""图层混合与合成。像素均为 straight-alpha RGBA。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from . import CLIP_BOTTOM, CLIP_MIDDLE, CLIP_TOP


def _rgb_to_hsl(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx = np.max(rgb, axis=-1)
    mn = np.min(rgb, axis=-1)
    l = (mx + mn) * 0.5
    d = mx - mn
    s = np.where(d == 0, 0.0, d / np.where(l < 0.5, mx + mn, 2.0 - mx - mn + 1e-12))
    h = np.zeros_like(l)
    nz = d > 0
    rc = np.where(nz, (mx - r) / np.where(nz, d, 1), 0)
    gc = np.where(nz, (mx - g) / np.where(nz, d, 1), 0)
    bc = np.where(nz, (mx - b) / np.where(nz, d, 1), 0)
    h = np.where((mx == r) & nz, bc - gc, h)
    h = np.where((mx == g) & nz, 2.0 + rc - bc, h)
    h = np.where((mx == b) & nz, 4.0 + gc - rc, h)
    h = (h / 6.0) % 1.0
    return h, s, l


def _hsl_to_rgb(h: np.ndarray, s: np.ndarray, l: np.ndarray) -> np.ndarray:
    def hue2rgb(p, q, t):
        t = t % 1.0
        cond1 = t < 1 / 6
        cond2 = t < 0.5
        cond3 = t < 2 / 3
        res = np.where(cond1, p + (q - p) * 6 * t, 0.0)
        res = np.where(cond2, q, res)
        res = np.where(cond3, p + (q - p) * (2 / 3 - t) * 6, res)
        return np.where(~(cond1 | cond2 | cond3), p, res)

    q = np.where(l < 0.5, l * (1 + s), l + s - l * s)
    p = 2 * l - q
    r = hue2rgb(p, q, h + 1 / 3)
    g = hue2rgb(p, q, h)
    b = hue2rgb(p, q, h - 1 / 3)
    return np.stack([r, g, b], axis=-1)


def blend_rgb(cb: np.ndarray, cs: np.ndarray, mode: int) -> np.ndarray:
    """cb=backdrop, cs=source，均为 0..1 的 RGB。"""
    if mode == 0:  # NORMAL
        return cs
    if mode == 1:  # MULTIPLY
        return cb * cs
    if mode == 2:  # SCREEN
        return 1 - (1 - cb) * (1 - cs)
    if mode == 3:  # LINEAR_DODGE
        return np.minimum(1, cb + cs)
    if mode == 4:  # DARK (变暗)
        return np.minimum(cb, cs)
    if mode == 5:  # COLOR_BURN
        return np.where(cs <= 0, 0.0, 1 - np.minimum(1, (1 - cb) / np.maximum(cs, 1e-6)))
    if mode == 6:  # COLOR_DODGE
        return np.where(cs >= 1, 1.0, np.minimum(1, cb / np.maximum(1 - cs, 1e-6)))
    if mode == 7:  # OVERLAY
        return np.where(cb <= 0.5, 2 * cb * cs, 1 - 2 * (1 - cb) * (1 - cs))
    if mode == 8:  # SOFT_LIGHT
        d = np.where(cb <= 0.25, ((16 * cb - 12) * cb + 4) * cb, np.sqrt(np.maximum(cb, 0)))
        return np.where(cs <= 0.5, cb - (1 - 2 * cs) * cb * (1 - cb),
                        cb + (2 * cs - 1) * (d - cb))
    if mode == 9:  # DIVIDE
        return np.where(cs <= 0, 1.0, np.minimum(1, cb / np.maximum(cs, 1e-6)))
    if mode == 10:  # COLOR
        h, s, _ = _rgb_to_hsl(cs)
        _, _, lb = _rgb_to_hsl(cb)
        return _hsl_to_rgb(h, s, lb)
    if mode == 11:  # LUMINOSITY
        _, _, ls = _rgb_to_hsl(cs)
        hb, sb, _ = _rgb_to_hsl(cb)
        return _hsl_to_rgb(hb, sb, ls)
    if mode == 12:  # SATURATION
        _, ss, _ = _rgb_to_hsl(cs)
        hb, _, lb = _rgb_to_hsl(cb)
        return _hsl_to_rgb(hb, ss, lb)
    if mode == 14:  # LINEAR_BURN
        return np.maximum(0, cb + cs - 1)
    if mode == 15:  # DARKER_COLOR
        return np.where(cb.sum(-1, keepdims=True) <= cs.sum(-1, keepdims=True), cb, cs)
    if mode == 16:  # LIGHTEN
        return np.maximum(cb, cs)
    if mode == 17:  # LIGHTER_COLOR
        return np.where(cb.sum(-1, keepdims=True) >= cs.sum(-1, keepdims=True), cb, cs)
    if mode == 18:  # HARD_LIGHT
        return np.where(cs <= 0.5, 2 * cb * cs, 1 - 2 * (1 - cb) * (1 - cs))
    if mode == 19:  # VIVID_LIGHT
        return np.where(cs <= 0.5,
                        np.where(cb <= 0, 0.0, 1 - np.minimum(1, (1 - cb) / np.maximum(2 * cs, 1e-6))),
                        np.where(cb >= 1, 1.0, np.minimum(1, cb / np.maximum(2 * (1 - cs), 1e-6))))
    if mode == 20:  # LINEAR_LIGHT
        return np.clip(cb + 2 * cs - 1, 0, 1)
    if mode == 21:  # PIN_LIGHT
        return np.where(cs <= 0.5, np.minimum(cb, 2 * cs), np.maximum(cb, 2 * cs - 1))
    if mode == 22:  # HARD_MIX
        return np.where(cb + cs >= 1, 1.0, 0.0)
    if mode == 23:  # DIFFERENCE
        return np.abs(cb - cs)
    if mode == 24:  # EXCLUSION
        return cb + cs - 2 * cb * cs
    if mode == 25:  # SUBTRACT
        return np.maximum(0, cb - cs)
    if mode == 26:  # HUE
        hs, _, _ = _rgb_to_hsl(cs)
        _, sb, lb = _rgb_to_hsl(cb)
        return _hsl_to_rgb(hs, sb, lb)
    # DISSOLVE / GLOW / PASS_THROUGH / GROUP_NORMAL 及未知模式：按普通叠加近似
    return cs


def _composite_band(
    dst: np.ndarray,
    src: np.ndarray,
    opacity: float,
    mode: int,
    clip_alpha: Optional[np.ndarray],
) -> None:
    """把 straight-alpha 的 src 以 src-over 方式叠加到 dst（原地修改）。"""
    cb = dst[..., :3]
    ab = dst[..., 3:4]
    cs = src[..., :3]
    as_ = src[..., 3:4] * opacity
    if clip_alpha is not None:
        as_ = as_ * clip_alpha[..., None]
    if not np.any(as_):
        return

    b = blend_rgb(cb, cs, mode)
    ao = as_ + ab * (1 - as_)
    safe = np.maximum(ao, 1e-6)
    co = (as_ * (1 - ab) * cs + as_ * ab * b + (1 - as_) * ab * cb) / safe
    dst[..., :3] = co
    dst[..., 3:4] = ao


@dataclass
class CompositeEntry:
    pixels: np.ndarray
    opacity: float
    visible: bool
    blend_mode: int
    clip_type: int = 0
    clip_group: int = 0
    name: str = ""


def _clip_base_map(entries: list[CompositeEntry]) -> dict[int, int]:
    """clipGroupId -> 基础层索引（MASK_BOTTOM）。"""
    bases: dict[int, int] = {}
    for i, e in enumerate(entries):
        if e.clip_type == CLIP_BOTTOM and e.clip_group and e.clip_group not in bases:
            bases[e.clip_group] = i
    return bases


def composite(
    width: int,
    height: int,
    entries: list[CompositeEntry],
    bg_rgba: Optional[tuple[int, int, int, int]] = None,
    band_rows: int = 512,
) -> np.ndarray:
    """按自下而上的顺序合成，返回 HxWx4 uint8（straight alpha）。"""
    result = np.zeros((height, width, 4), dtype=np.uint8)
    bases = _clip_base_map(entries)
    base_visible = {gid: entries[i].visible for gid, i in bases.items()}

    for y0 in range(0, height, band_rows):
        y1 = min(height, y0 + band_rows)
        bh = y1 - y0
        dst = np.zeros((bh, width, 4), dtype=np.float32)

        if bg_rgba is not None:
            r, g, b, a = bg_rgba
            dst[..., 0] = r / 255.0
            dst[..., 1] = g / 255.0
            dst[..., 2] = b / 255.0
            dst[..., 3] = a / 255.0

        # 预先取出这一带每个剪贴组基础层的 alpha
        band_base_alpha: dict[int, np.ndarray] = {}
        for gid, idx in bases.items():
            base = entries[idx]
            band_base_alpha[gid] = (
                base.pixels[y0:y1, :, 3].astype(np.float32) / 255.0
            )

        for e in entries:
            if not e.visible:
                continue
            clip_alpha = None
            if e.clip_type in (CLIP_TOP, CLIP_MIDDLE) and e.clip_group in bases:
                if not base_visible.get(e.clip_group, True):
                    continue
                clip_alpha = band_base_alpha.get(e.clip_group)
            src = e.pixels[y0:y1].astype(np.float32) / 255.0
            _composite_band(dst, src, e.opacity, e.blend_mode, clip_alpha)

        result[y0:y1] = np.clip(dst * 255.0 + 0.5, 0, 255).astype(np.uint8)
    return result


