"""最小但完整的 8-bit RGB PSD 写入器。

支持：任意数量栅格图层、图层名（含中文）、不透明度、可见性、
剪贴蒙版标记、混合模式、锁透明度标记、合并预览图。
图层组会被扁平化（由调用方完成）。
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

import numpy as np

# 画世界 BlendMode -> PSD blend key
PSD_BLEND_KEYS = {
    0: b"norm",
    1: b"mul ",
    2: b"scrn",
    3: b"lddg",   # LINEAR_DODGE
    4: b"dark",   # DARK
    5: b"idiv",   # COLOR_BURN
    6: b"div ",   # COLOR_DODGE
    7: b"over",
    8: b"sLit",
    9: b"fdiv",   # DIVIDE
    10: b"colr",
    11: b"lum ",
    12: b"sat ",
    13: b"diss",
    14: b"lbrn",
    15: b"dkCl",
    16: b"lite",
    17: b"lgCl",
    18: b"hLit",
    19: b"vLit",
    20: b"lLit",
    21: b"pLit",
    22: b"hMix",   # HARD_MIX
    23: b"diff",
    24: b"smud",
    25: b"fsub",   # SUBTRACT
    26: b"hue ",
    27: b"norm",   # GLOW 近似
    28: b"pass",
    29: b"norm",
}

CHANNEL_IDS = (0, 1, 2, -1)  # R, G, B, A


@dataclass
class PsdLayer:
    name: str
    pixels: np.ndarray  # HxWx4 uint8
    opacity: float = 1.0
    visible: bool = True
    blend_mode: int = 0
    clipping: bool = False
    lock_alpha: bool = False


def _packbits_row(row: np.ndarray) -> bytes:
    n = int(row.size)
    if n == 0:
        return b""
    changes = np.flatnonzero(row[1:] != row[:-1]) + 1
    # 短游程很多的行直接按字面量编码，避免 Python 层循环过多
    if changes.size + 1 > max(8, n // 8):
        out = bytearray()
        for start in range(0, n, 128):
            chunk = row[start:start + 128].tobytes()
            out.append(len(chunk) - 1)
            out.extend(chunk)
        return bytes(out)

    bounds = np.concatenate(([0], changes, [n]))
    out = bytearray()

    def flush_literals(a: int, b: int) -> None:
        while a < b:
            e = min(a + 128, b)
            chunk = row[a:e].tobytes()
            out.append(e - a - 1)
            out.extend(chunk)
            a = e

    lit_start = 0
    for i in range(len(bounds) - 1):
        a = int(bounds[i])
        b = int(bounds[i + 1])
        run = b - a
        if run >= 3:
            flush_literals(lit_start, a)
            value = int(row[a])
            while run > 0:
                take = min(run, 128)
                out.append((257 - take) & 0xFF)
                out.append(value)
                a += take
                run -= take
            lit_start = b
    flush_literals(lit_start, n)
    return bytes(out)


def _rle_plane(plane: np.ndarray) -> bytes:
    h = plane.shape[0]
    counts = bytearray(2 * h)
    rows: list[bytes] = []
    for y in range(h):
        enc = _packbits_row(plane[y])
        if len(enc) > 0xFFFF:
            raise ValueError("RLE 行过长，无法写入 PSD")
        counts[2 * y:2 * y + 2] = len(enc).to_bytes(2, "big")
        rows.append(enc)
    return bytes(counts) + b"".join(rows)


def _u16(v: int) -> bytes:
    return struct.pack(">H", v)


def _u32(v: int) -> bytes:
    return struct.pack(">I", v)


def _even_pad(data: bytes) -> bytes:
    return data + (b"\x00" if len(data) % 2 else b"")


def _pascal_name(name: str) -> bytes:
    raw = name.encode("utf-8", "replace")[:255]
    data = bytes([len(raw)]) + raw
    if len(data) % 4:
        data += b"\x00" * (4 - len(data) % 4)
    return data


def _luni_block(name: str) -> bytes:
    uni = name.encode("utf-16-be", "replace")
    payload = _u32(len(uni) // 2) + uni
    if len(payload) % 2:
        payload += b"\x00"
    return b"8BIM" + b"luni" + _u32(len(payload)) + payload


def _crop_layer(pixels: np.ndarray) -> tuple[np.ndarray, int, int, int, int]:
    """裁到 alpha 非零区域，返回 (crop, top, left, bottom, right)。"""
    if pixels is None:
        rgba = np.zeros((1, 1, 4), dtype=np.uint8)
        return rgba, 0, 0, 1, 1
    alpha = pixels[..., 3]
    cols = np.any(alpha, axis=0)
    rows = np.any(alpha, axis=1)
    if not cols.any() or not rows.any():
        rgba = np.zeros((1, 1, 4), dtype=np.uint8)
        return rgba, 0, 0, 1, 1
    left = int(np.argmax(cols))
    right = int(len(cols) - np.argmax(cols[::-1]))
    top = int(np.argmax(rows))
    bottom = int(len(rows) - np.argmax(rows[::-1]))
    return pixels[top:bottom, left:right], top, left, bottom, right


def _layer_channel_blob(channel: np.ndarray) -> bytes:
    return b"\x00\x01" + _rle_plane(channel)


def _build_layer_record(layer: PsdLayer) -> tuple[bytes, bytes]:
    crop, top, left, bottom, right = _crop_layer(layer.pixels)

    channel_blobs: list[bytes] = []
    for c in range(4):
        channel_blobs.append(_layer_channel_blob(crop[..., c]))

    key = PSD_BLEND_KEYS.get(layer.blend_mode, b"norm")
    opacity = max(0, min(255, int(round(layer.opacity * 255))))
    flags = 0x08
    if not layer.visible:
        flags |= 0x02
    if layer.lock_alpha:
        flags |= 0x01

    extra = _u32(0)  # layer mask data
    extra += _u32(0)  # blending ranges
    extra += _pascal_name(layer.name)
    extra += _luni_block(layer.name)
    if len(extra) % 2:
        extra += b"\x00"

    rec = bytearray()
    rec += struct.pack(">iiii", top, left, bottom, right)
    rec += _u16(4)
    for cid, blob in zip(CHANNEL_IDS, channel_blobs):
        rec += struct.pack(">hI", cid, len(blob))
    rec += b"8BIM" + key
    rec += bytes((opacity, 1 if layer.clipping else 0, flags, 0))
    rec += _u32(len(extra))
    rec += extra
    if len(rec) % 2:
        rec += b"\x00"

    return bytes(rec), b"".join(channel_blobs)


def _resolution_resource(ppi: int) -> bytes:
    if ppi <= 0:
        return b""
    fixed = int(round(ppi * 65536))
    data = struct.pack(">IHHIHH", fixed, 1, 1, fixed, 1, 1)
    # 8BIM + id + 空名称(2 字节) + size + data
    block = b"8BIM" + _u16(1005) + b"\x00\x00" + _u32(len(data)) + data
    return _even_pad(block)


def write_psd(
    path: str,
    width: int,
    height: int,
    layers: list[PsdLayer],
    merged_rgba: np.ndarray,
    ppi: int = 72,
) -> None:
    if merged_rgba.shape != (height, width, 4):
        raise ValueError("合并预览图尺寸与画布不一致")
    if not (1 <= width <= 30000 and 1 <= height <= 30000):
        raise ValueError(f"PSD 不支持 {width}x{height}（上限 30000）")
    if len(layers) > 30000:
        raise ValueError("图层数量过多")

    header = (
        b"8BPS" + _u16(1) + b"\x00" * 6 +
        _u16(4) + _u32(height) + _u32(width) + _u16(8) + _u16(3)
    )

    resources = _resolution_resource(ppi)
    image_resources = _u32(len(resources)) + resources

    records: list[bytes] = []
    channel_data: list[bytes] = []
    for layer in layers:
        rec, chans = _build_layer_record(layer)
        records.append(rec)
        channel_data.append(chans)

    layer_info = _u16(len(layers)) + b"".join(records) + b"".join(channel_data)
    if len(layer_info) % 2:
        layer_info += b"\x00"

    layer_and_mask = _u32(len(layer_info)) + layer_info + _u32(0)

    # 合并预览图（4 通道，RLE）
    counts = bytearray()
    rows: list[bytes] = []
    for c in range(4):
        plane = merged_rgba[..., c]
        for y in range(height):
            enc = _packbits_row(plane[y])
            if len(enc) > 0xFFFF:
                raise ValueError("合并预览行过长")
            counts += len(enc).to_bytes(2, "big")
            rows.append(enc)
    image_data = _u16(1) + bytes(counts) + b"".join(rows)

    with open(path, "wb") as f:
        f.write(header)
        f.write(_u32(0))  # color mode data
        f.write(image_resources)
        f.write(_u32(len(layer_and_mask)))
        f.write(layer_and_mask)
        f.write(image_data)
