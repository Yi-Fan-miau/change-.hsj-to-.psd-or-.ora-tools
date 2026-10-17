#!/usr/bin/env python3
"""画世界Pro .hsj 多图层草稿 -> PSD / ORA 转换器。

用法:
    python hsj2psd.py 草稿.hsj
    python hsj2psd.py 草稿.hsj -o 输出.psd
    python hsj2psd.py 草稿.hsj --format both
    python hsj2psd.py 草稿.hsj --list
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Optional

import numpy as np

from hsjconv import (
    CLIP_BOTTOM,
    CLIP_MIDDLE,
    CLIP_TOP,
    DrawData,
    HsjError,
    LayerInfo,
    build_layer_tree,
    decode_layer,
    flatten_for_psd,
    layer_canvas_size,
    load_hsj,
    parse_draw_data,
)
from hsjconv.blend import CompositeEntry, composite
from hsjconv.ora import write_ora
from hsjconv.psd import PsdLayer, write_psd


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _argb(parts: int) -> tuple[int, int, int, int]:
    c = parts & 0xFFFFFFFF
    return (c >> 24) & 0xFF, (c >> 16) & 0xFF, (c >> 8) & 0xFF, c & 0xFF


def _choose_paint(pkg, log=_log) -> tuple[Optional[str], Optional[DrawData]]:
    best_name: Optional[str] = None
    best: Optional[DrawData] = None
    # paint_as 通常是最新自动保存；两者都有图层时优先图层更多的
    for name in ("paint_as.dat", "paint.dat"):
        blob = pkg.get(name)
        if not blob:
            continue
        try:
            dd = parse_draw_data(blob)
        except HsjError as exc:
            log(f"警告: {name} 解析失败：{exc}")
            continue
        if best is None or len(dd.layers) > len(best.layers):
            best_name, best = name, dd
    return best_name, best


def _collect_leaves(items: list[LayerInfo]) -> list[LayerInfo]:
    out: list[LayerInfo] = []
    for item in items:
        if item.is_group:
            out.extend(_collect_leaves(item.children))
        else:
            out.append(item)
    return out


def _fit_canvas(pixels: np.ndarray, width: int, height: int) -> np.ndarray:
    if pixels.shape == (height, width, 4):
        return pixels
    out = np.zeros((height, width, 4), dtype=np.uint8)
    h = min(height, pixels.shape[0])
    w = min(width, pixels.shape[1])
    out[:h, :w] = pixels[:h, :w]
    return out


def load_draft(path: str, with_bg: bool = True, load_pixels: bool = True, log=_log):
    pkg = load_hsj(path)
    paint_name, draw = _choose_paint(pkg, log=log)
    if draw is None:
        draw = DrawData()

    roots = build_layer_tree(draw.layers)
    if not roots:
        # 没有图层元数据时，退化为按 layers/ 文件名顺序输出
        ids = pkg.layer_ids()
        if not ids:
            raise HsjError("草稿中既没有图层元数据，也没有图层文件")
        roots = [
            LayerInfo(id=lid, name=f"图层 {i + 1}", opacity=1.0, visible=True)
            for i, lid in enumerate(ids)
        ]
        log(f"提示: 未找到图层元数据，按文件名顺序重建 {len(ids)} 个图层")

    width = draw.canvas_width
    height = draw.canvas_height

    leaves = _collect_leaves(roots)
    if not leaves:
        raise HsjError("草稿中没有可转换的图层")

    if width <= 0 or height <= 0:
        for layer in leaves:
            blob = pkg.get(f"layers/{layer.id}")
            if blob is not None:
                width, height = layer_canvas_size(blob)
                break
    if width <= 0 or height <= 0:
        raise HsjError("无法确定画布尺寸")

    if load_pixels:
        for layer in leaves:
            blob = pkg.get(f"layers/{layer.id}")
            if blob is None:
                layer.pixels = np.zeros((height, width, 4), dtype=np.uint8)
                continue
            try:
                layer.pixels = decode_layer(blob)
            except HsjError as exc:
                log(f"警告: 图层 {layer.name or layer.id} 解码失败：{exc}")
                layer.pixels = np.zeros((height, width, 4), dtype=np.uint8)
        for layer in leaves:
            layer.pixels = _fit_canvas(layer.pixels, width, height)

    bg_layer: Optional[LayerInfo] = None
    bg_rgba: Optional[tuple[int, int, int, int]] = None
    a, r, g, b = _argb(draw.bg_color)
    if with_bg and not draw.bg_hidden and a > 0:
        bg_rgba = (r, g, b, a)
        bg_pixels = None
        if load_pixels:
            bg_pixels = np.empty((height, width, 4), dtype=np.uint8)
            bg_pixels[..., 0] = r
            bg_pixels[..., 1] = g
            bg_pixels[..., 2] = b
            bg_pixels[..., 3] = a
        bg_layer = LayerInfo(
            id="__background__",
            name="背景",
            opacity=1.0,
            visible=True,
            pixels=bg_pixels,
        )
        roots = [bg_layer] + roots

    return {
        "pkg": pkg,
        "draw": draw,
        "roots": roots,
        "width": width,
        "height": height,
        "bg_rgba": bg_rgba,
        "paint_name": paint_name,
    }


def _flatten_and_entries(roots: list[LayerInfo]):
    flat = flatten_for_psd(roots)
    entries: list[CompositeEntry] = []
    for layer, name, opacity, visible in flat:
        entries.append(CompositeEntry(
            pixels=layer.pixels,
            opacity=opacity,
            visible=visible,
            blend_mode=layer.blend_mode,
            clip_type=layer.clip_type,
            clip_group=layer.clip_group,
            name=name,
        ))
    return flat, entries


def convert(path: str, output: str, fmt: str, with_bg: bool = True,
            force: bool = False, log=_log) -> list[str]:
    t0 = time.time()
    log(f"读取 {os.path.basename(path)} ...")
    data = load_draft(path, with_bg=with_bg, log=log)
    width, height = data["width"], data["height"]
    draw: DrawData = data["draw"]
    paint_name = data["paint_name"] or "（无图层元数据）"
    log(f"画布 {width} x {height}，图层 {len(_collect_leaves(data['roots']))} 个，"
         f"元数据 {paint_name}")
    if draw.color_space:
        log(f"色彩空间: {draw.color_space}（PSD/ORA 中不嵌入 ICC 配置）")

    flat, entries = _flatten_and_entries(data["roots"])
    log("合成预览图 ...")
    # 背景色已经作为最底层的“背景”图层加入 roots，避免与 bg_rgba 重复叠加
    merged = composite(width, height, entries, bg_rgba=None)

    def _ensure_parent(out_path: str) -> None:
        parent = os.path.dirname(os.path.abspath(out_path))
        if parent:
            os.makedirs(parent, exist_ok=True)

    # PSD 的剪贴蒙版标记：基础层（MASK_BOTTOM）必须位于其下方
    bases: dict[int, int] = {}
    for i, (layer, _name, _op, _vis) in enumerate(flat):
        if layer.clip_type == CLIP_BOTTOM and layer.clip_group:
            bases.setdefault(layer.clip_group, i)

    outputs: list[str] = []
    psd_path = (output if fmt == "psd" else output + ".psd") if fmt in ("psd", "both") else None
    ora_path = (output if fmt == "ora" else output + ".ora") if fmt in ("ora", "both") else None

    # 先检查所有目标，避免只写出一半
    if not force:
        for target in (psd_path, ora_path):
            if target and os.path.exists(target):
                raise HsjError(f"输出文件已存在：{target}（使用 --force 覆盖）")

    if psd_path:
        log("写入 PSD ...")
        psd_layers = []
        for i, (layer, name, opacity, visible) in enumerate(flat):
            clipping = (
                layer.clip_type in (CLIP_TOP, CLIP_MIDDLE)
                and layer.clip_group in bases
                and bases[layer.clip_group] < i
            )
            psd_layers.append(PsdLayer(
                name=name or f"图层 {i + 1}",
                pixels=layer.pixels,
                opacity=opacity,
                visible=visible,
                blend_mode=layer.blend_mode,
                clipping=clipping,
                lock_alpha=layer.is_lock_alpha,
            ))
        _ensure_parent(psd_path)
        write_psd(psd_path, width, height, psd_layers, merged, ppi=draw.ppi)
        outputs.append(psd_path)

    if ora_path:
        log("写入 ORA ...")
        _ensure_parent(ora_path)
        write_ora(ora_path, width, height, data["roots"], merged)
        outputs.append(ora_path)

    log(f"完成，用时 {time.time() - t0:.1f}s")
    return outputs


def print_layer_list(path: str, with_bg: bool = True) -> None:
    data = load_draft(path, with_bg=with_bg, load_pixels=False)
    draw: DrawData = data["draw"]
    print(f"画布: {data['width']} x {data['height']}，PPI: {draw.ppi}")
    if draw.color_space:
        print(f"色彩空间: {draw.color_space}")
    print(f"背景色: {'隐藏' if data['bg_rgba'] is None else data['bg_rgba']}")
    print("图层（自下而上）:")
    for i, (layer, name, opacity, visible) in enumerate(
            flatten_for_psd(data["roots"])):
        flags = []
        if not visible:
            flags.append("隐藏")
        if layer.clip_type in (CLIP_TOP, CLIP_MIDDLE):
            flags.append(f"剪贴组{layer.clip_group}")
        if layer.is_lock_alpha:
            flags.append("锁透明")
        extra = ("  [" + ", ".join(flags) + "]") if flags else ""
        print(f"  {i + 1:3d}. {name}  不透明度={opacity * 100:.0f}%  "
              f"混合={layer.blend_name}{extra}")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="把画世界Pro导出的 .hsj 多图层草稿转换为 PSD 或 ORA",
    )
    parser.add_argument("input", help="输入的 .hsj 文件")
    parser.add_argument("-o", "--output",
                        help="输出文件；both 模式下作为不带扩展名的前缀")
    parser.add_argument("--format", choices=("psd", "ora", "both"),
                        default="psd", help="输出格式（默认 psd）")
    parser.add_argument("--list", action="store_true", help="只列出图层信息")
    parser.add_argument("--no-bg", action="store_true",
                        help="不输出画布背景色图层")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的输出")
    args = parser.parse_args(argv)

    try:
        if args.list:
            print_layer_list(args.input, with_bg=not args.no_bg)
            return 0
        stem = os.path.splitext(args.input)[0]
        if args.format == "psd":
            output = args.output or stem + ".psd"
        elif args.format == "ora":
            output = args.output or stem + ".ora"
        else:
            output = args.output or stem
            output = os.path.splitext(output)[0]
        outputs = convert(args.input, output, args.format,
                          with_bg=not args.no_bg, force=args.force)
        for out in outputs:
            print(out)
        return 0
    except HsjError as exc:
        _log(f"错误: {exc}")
        return 1
    except (OSError, ValueError) as exc:
        _log(f"错误: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
