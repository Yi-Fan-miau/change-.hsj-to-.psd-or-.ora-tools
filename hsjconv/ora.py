"""OpenRaster (.ora) 写入器。

ORA 是 Krita / GIMP / MyPaint 等通用的多图层格式（ZIP + PNG 图层 + XML）。
说明：ORA 标准没有剪贴蒙版，因此这里会把剪贴蒙版烘焙进图层的 alpha 通道，
      视觉效果与画世界一致，但该图层不再是“可解除”的剪贴层。
"""

from __future__ import annotations

import io
import os
import zipfile
from xml.sax.saxutils import escape


def _xml_attr(text: str) -> str:
    clean = "".join(
        ch if ord(ch) >= 0x20 or ch in "\t\n\r" else " "
        for ch in text
    )
    return escape(clean, {'"': "&quot;", "'": "&apos;"})

import numpy as np
from PIL import Image

from . import CLIP_BOTTOM, CLIP_MIDDLE, CLIP_TOP, LayerInfo

SVG_BLEND = {
    0: "svg:normal",
    1: "svg:multiply",
    2: "svg:screen",
    3: "svg:screen",          # LINEAR_DODGE 近似
    4: "svg:darken",
    5: "svg:color-burn",
    6: "svg:color-dodge",
    7: "svg:overlay",
    8: "svg:soft-light",
    9: "svg:normal",          # DIVIDE
    10: "svg:color",
    11: "svg:luminosity",
    12: "svg:saturation",
    13: "svg:normal",         # DISSOLVE
    14: "svg:multiply",       # LINEAR_BURN 近似
    15: "svg:darken",         # DARKER_COLOR
    16: "svg:lighten",
    17: "svg:lighten",        # LIGHTER_COLOR
    18: "svg:hard-light",
    19: "svg:hard-light",     # VIVID_LIGHT 近似
    20: "svg:normal",         # LINEAR_LIGHT
    21: "svg:normal",         # PIN_LIGHT
    22: "svg:normal",         # HARD_MIX
    23: "svg:difference",
    24: "svg:exclusion",
    25: "svg:normal",         # SUBTRACT
    26: "svg:hue",
    27: "svg:normal",         # GLOW
    28: "svg:normal",
    29: "svg:normal",
}


def _png_bytes(pixels: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(pixels, "RGBA").save(buf, format="PNG", compress_level=6)
    return buf.getvalue()


def _crop(pixels: np.ndarray) -> tuple[np.ndarray, int, int]:
    alpha = pixels[..., 3]
    cols = np.any(alpha, axis=0)
    rows = np.any(alpha, axis=1)
    if not cols.any() or not rows.any():
        return np.zeros((1, 1, 4), dtype=np.uint8), 0, 0
    left = int(np.argmax(cols))
    right = int(len(cols) - np.argmax(cols[::-1]))
    top = int(np.argmax(rows))
    bottom = int(len(rows) - np.argmax(rows[::-1]))
    return pixels[top:bottom, left:right], left, top


def _bake_clipping(roots: list[LayerInfo]) -> dict[str, np.ndarray]:
    """返回被剪贴图层的新像素表（layer.id -> pixels）。"""
    leaves: list[LayerInfo] = []

    def walk(items: list[LayerInfo]):
        for item in items:
            if item.is_group:
                walk(item.children)
            else:
                leaves.append(item)

    walk(roots)

    bases: dict[int, LayerInfo] = {}
    for layer in leaves:
        if layer.clip_type == CLIP_BOTTOM and layer.clip_group:
            bases.setdefault(layer.clip_group, layer)

    baked: dict[str, np.ndarray] = {}
    for layer in leaves:
        if layer.clip_type not in (CLIP_TOP, CLIP_MIDDLE):
            continue
        base = bases.get(layer.clip_group)
        if base is None or base.pixels is None or layer.pixels is None:
            continue
        if base.pixels.shape != layer.pixels.shape:
            continue
        out = layer.pixels.copy()
        out[..., 3] = (
            out[..., 3].astype(np.uint16) * base.pixels[..., 3] // 255
        ).astype(np.uint8)
        baked[layer.id] = out
    return baked


def _stack_xml(
    items: list[LayerInfo],
    baked: dict[str, np.ndarray],
    image_files: dict[str, tuple[str, int, int]],
    level: int,
) -> list[str]:
    indent = "  " * level
    lines: list[str] = []
    for item in items:
        name = _xml_attr(item.name or "Layer")
        vis = "visible" if item.visible else "hidden"
        op = f"{max(0.0, min(1.0, item.opacity)):.4f}"
        blend = SVG_BLEND.get(item.blend_mode, "svg:normal")
        if item.is_group:
            lines.append(
                f'{indent}<stack name="{name}" visibility="{vis}" '
                f'opacity="{op}" composite-op="{blend}" isolation="isolate">'
            )
            lines.extend(_stack_xml(item.children, baked, image_files, level + 1))
            lines.append(f"{indent}</stack>")
        else:
            src, x, y = image_files[item.id]
            lines.append(
                f'{indent}<layer name="{name}" src="{src}" x="{x}" y="{y}" '
                f'visibility="{vis}" opacity="{op}" composite-op="{blend}"/>'
            )
    return lines


def write_ora(
    path: str,
    width: int,
    height: int,
    roots: list[LayerInfo],
    merged_rgba: np.ndarray,
) -> None:
    if merged_rgba.shape != (height, width, 4):
        raise ValueError("合并预览图尺寸与画布不一致")
    baked = _bake_clipping(roots)
    image_files: dict[str, tuple[str, int, int]] = {}
    layer_blobs: list[tuple[str, bytes]] = []
    idx = 0

    def walk(items: list[LayerInfo]):
        nonlocal idx
        for item in items:
            if item.is_group:
                walk(item.children)
                continue
            pixels = baked.get(item.id)
            if pixels is None:
                pixels = item.pixels
            if pixels is None:
                pixels = np.zeros((height, width, 4), dtype=np.uint8)
            crop, x, y = _crop(pixels)
            name = f"data/layer{idx}.png"
            idx += 1
            image_files[item.id] = (name, x, y)
            layer_blobs.append((name, _png_bytes(crop)))

    walk(roots)

    xml = [
        "<?xml version='1.0' encoding='UTF-8'?>",
        f'<image version="0.0.2" w="{width}" h="{height}">',
        '  <stack name="root" visibility="visible" opacity="1.0000" composite-op="svg:normal">',
    ]
    xml.extend(_stack_xml(roots, baked, image_files, 2))
    xml.append("  </stack>")
    xml.append("</image>")
    stack_xml = "\n".join(xml).encode("utf-8")

    merged_buf = io.BytesIO()
    Image.fromarray(merged_rgba, "RGBA").save(merged_buf, format="PNG", compress_level=6)

    tmp_path = path + ".tmp"
    with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "image/openraster", compress_type=zipfile.ZIP_STORED)
        zf.writestr("stack.xml", stack_xml)
        zf.writestr("mergedimage.png", merged_buf.getvalue())
        for name, blob in layer_blobs:
            zf.writestr(name, blob)
    os.replace(tmp_path, path)
