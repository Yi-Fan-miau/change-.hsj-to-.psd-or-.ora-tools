"""
画世界Pro .hsj 草稿解析器。

格式概要（逆向自画世界Pro 3.4.6）：
- .hsj 是一个 ZIP，通常只包含一个名为 "0" 的条目；
- "0" 的布局：
    0x00  "8E9E23DF"          8 字节魔数
    0x08  int32 BE            版本号（当前 41）
    0x0C  int64 BE            文件总长度
    0x14  int64 BE            文件索引(footer)偏移
    0x1C  int64 BE            文件索引长度
    0x24..0xC7                零填充（数据区从 0xC8=200 开始）
    0xC8..footer_offset       草稿文件数据区（paint.dat、layers/* 等）
    footer_offset..EOF        ExportDraftInfo protobuf（含文件路径/偏移/长度）
- 图层文件 layers/<uuid>：
    magic "hsj\\0" + 版本(3字节) + 画布宽/高 + bbox + 分条数据。
    版本1：每条 = 24字节头 + LZ4 block 压缩的 RGBA（行从下到上）；
    版本2：每条 = Zstd 帧压缩的 RGBA（行从下到上）。
- paint.dat / paint_as.dat：DrawData protobuf，其中 mpLayers["0"].layers
  保存图层栈（自下而上），含不透明度、可见性、混合模式、剪贴蒙版等信息。

本模块只依赖 numpy / lz4 / zstandard。
"""

from __future__ import annotations

import io
import struct
import zipfile
from dataclasses import dataclass, field
from typing import Iterator, Optional

import lz4.block
import numpy as np
import zstandard

HSJ_CONTAINER_MAGIC = b"8E9E23DF"
LAYER_MAGIC = b"hsj\x00"
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"

# LayerInfo.BlendMode
BLEND_NAMES = {
    0: "NORMAL", 1: "MULTIPLY", 2: "SCREEN", 3: "LINEAR_DODGE", 4: "DARK",
    5: "COLOR_BURN", 6: "COLOR_DODGE", 7: "OVERLAY", 8: "SOFT_LIGHT",
    9: "DIVIDE", 10: "COLOR", 11: "LUMINOSITY", 12: "SATURATION",
    13: "DISSOLVE", 14: "LINEAR_BURN", 15: "DARKER_COLOR", 16: "LIGHTEN",
    17: "LIGHTER_COLOR", 18: "HARD_LIGHT", 19: "VIVID_LIGHT",
    20: "LINEAR_LIGHT", 21: "PIN_LIGHT", 22: "HARD_MIX", 23: "DIFFERENCE",
    24: "EXCLUSION", 25: "SUBTRACT", 26: "HUE", 27: "GLOW",
    28: "PASS_THROUGH", 29: "GROUP_NORMAL",
}

# LayerInfo.ClipMaskType
CLIP_NONE, CLIP_TOP, CLIP_MIDDLE, CLIP_BOTTOM = 0, 1, 2, 3


class HsjError(Exception):
    """无法解析的 .hsj / 草稿数据。"""


# ---------------------------------------------------------------------------
# protobuf wire 解析（只依赖 wire 格式，不需要 .proto 文件）
# ---------------------------------------------------------------------------

def _read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        if pos >= len(buf):
            raise HsjError("protobuf varint 被截断")
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, pos
        shift += 7
        if shift > 70:
            raise HsjError("protobuf varint 过长")


def _iter_fields(buf: bytes) -> Iterator[tuple[int, int, object]]:
    """依次产出 (field_number, wire_type, value)。"""
    pos = 0
    n = len(buf)
    while pos < n:
        tag, pos = _read_varint(buf, pos)
        fn, wt = tag >> 3, tag & 7
        if fn == 0:
            raise HsjError("protobuf 字段号为 0")
        if wt == 0:
            val, pos = _read_varint(buf, pos)
        elif wt == 1:
            if pos + 8 > n:
                raise HsjError("protobuf fixed64 被截断")
            val = buf[pos:pos + 8]
            pos += 8
        elif wt == 2:
            ln, pos = _read_varint(buf, pos)
            if pos + ln > n:
                raise HsjError("protobuf 长度字段被截断")
            val = buf[pos:pos + ln]
            pos += ln
        elif wt == 5:
            if pos + 4 > n:
                raise HsjError("protobuf fixed32 被截断")
            val = buf[pos:pos + 4]
            pos += 4
        else:
            raise HsjError(f"不支持的 protobuf wire type: {wt}")
        yield fn, wt, val


def _as_int32(v: int) -> int:
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v & 0x80000000 else v


def _as_uint64(v: int) -> int:
    return v & 0xFFFFFFFFFFFFFFFF


def _f32(raw: bytes) -> float:
    return struct.unpack("<f", raw)[0]


def _decode_text(raw: bytes) -> str:
    """画世界部分版本把中文图层名按 GBK 写入 protobuf string。"""
    if not raw:
        return ""
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class LayerInfo:
    id: str = ""
    name: str = ""
    opacity: float = 1.0
    visible: bool = True
    blend_mode: int = 0
    clip_type: int = 0
    clip_group: int = 0
    layer_no: int = 0
    is_group: bool = False
    is_lock: bool = False
    is_lock_alpha: bool = False
    parent_id: str = ""
    children: list["LayerInfo"] = field(default_factory=list)
    pixels: Optional[np.ndarray] = None  # HxWx4 uint8，惰性加载
    # proto3 标量字段没有 presence，这里记录原始字段是否出现，
    # 用于兼容“旧文件省略 visible 字段”的版本。
    visible_present: bool = False

    @property
    def blend_name(self) -> str:
        return BLEND_NAMES.get(self.blend_mode, f"UNKNOWN({self.blend_mode})")


@dataclass
class DrawData:
    canvas_width: int = 0
    canvas_height: int = 0
    bg_color: int = 0          # Android ARGB int
    bg_hidden: bool = False    # proto3 缺省 false；export2 显式写 true
    ppi: int = 72
    color_space: str = ""
    layers: list[LayerInfo] = field(default_factory=list)


@dataclass
class DraftPackage:
    folder_name: str
    files: dict[str, bytes]
    raw: bytes
    version: int

    def get(self, *names: str) -> Optional[bytes]:
        for name in names:
            for key, value in self.files.items():
                norm = key.lstrip("/")
                if norm == name or norm.endswith("/" + name):
                    return value
        return None

    def layer_ids(self) -> list[str]:
        ids = []
        for key in self.files:
            norm = key.lstrip("/")
            if norm.startswith("layers/"):
                lid = norm.split("/", 1)[1]
                if lid and lid != "sellayer":
                    ids.append(lid)
        return ids


# ---------------------------------------------------------------------------
# .hsj 容器
# ---------------------------------------------------------------------------

def _parse_export_footer(footer: bytes) -> tuple[str, list[tuple[str, int, int]]]:
    folder_name = ""
    entries: list[tuple[str, int, int]] = []
    for fn, wt, val in _iter_fields(footer):
        if fn == 1 and wt == 2:
            folder_name = bytes(val).decode("utf-8", "replace")
        elif fn == 12 and wt == 2:
            path = ""
            begin = 0
            length = 0
            for f2, w2, v2 in _iter_fields(bytes(val)):
                if f2 == 1 and w2 == 2:
                    path = bytes(v2).decode("utf-8", "replace")
                elif f2 == 2 and w2 == 0:
                    begin = int(v2)
                elif f2 == 3 and w2 == 0:
                    length = int(v2)
            if path:
                entries.append((path.lstrip("/"), begin, length))
    return folder_name, entries


def _parse_container(inner: bytes) -> DraftPackage:
    if len(inner) < 36 or inner[:8] != HSJ_CONTAINER_MAGIC:
        raise HsjError("不是有效的画世界导出草稿（魔数不匹配）")
    version = int.from_bytes(inner[8:12], "big")
    total_size = int.from_bytes(inner[12:20], "big")
    footer_off = int.from_bytes(inner[20:28], "big")
    footer_len = int.from_bytes(inner[28:36], "big")
    if footer_off + footer_len > len(inner) or footer_off < 36:
        raise HsjError("草稿索引越界，文件可能损坏")
    footer = inner[footer_off:footer_off + footer_len]
    folder_name, entries = _parse_export_footer(footer)
    files: dict[str, bytes] = {}
    for path, begin, length in entries:
        if begin < 0 or length < 0 or begin + length > len(inner):
            continue
        files[path] = inner[begin:begin + length]
    if not files:
        raise HsjError("草稿索引为空，文件可能损坏")
    return DraftPackage(folder_name=folder_name, files=files, raw=inner, version=version)


def load_hsj(path: str) -> DraftPackage:
    """读取 .hsj（ZIP 容器）或已解出的内部 "0" 文件。"""
    with open(path, "rb") as f:
        data = f.read()
    if data[:2] == b"PK":
        packages: list[DraftPackage] = []
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    blob = zf.read(info)
                    if blob[:8] == HSJ_CONTAINER_MAGIC:
                        packages.append(_parse_container(blob))
        except (zipfile.BadZipFile, RuntimeError) as exc:
            raise HsjError(f"ZIP 读取失败：{exc}") from exc
        if not packages:
            raise HsjError("ZIP 中没有找到画世界草稿数据")
        # 正常情况下只有一个；若有多个，合并文件表
        if len(packages) == 1:
            return packages[0]
        merged = DraftPackage(
            folder_name=packages[0].folder_name,
            files={},
            raw=packages[0].raw,
            version=packages[0].version,
        )
        for pkg in packages:
            merged.files.update(pkg.files)
        return merged
    if data[:8] == HSJ_CONTAINER_MAGIC:
        return _parse_container(data)
    raise HsjError("无法识别的文件：既不是 .hsj ZIP，也不是内部草稿数据")


# ---------------------------------------------------------------------------
# DrawData / LayerInfo
# ---------------------------------------------------------------------------

def _parse_layer_info(buf: bytes) -> LayerInfo:
    li = LayerInfo()
    fields: dict[int, object] = {}
    for fn, wt, val in _iter_fields(buf):
        if fn == 14 and wt == 2:
            li.children.append(_parse_layer_info(bytes(val)))
            fields[14] = True
        elif wt == 2:
            fields[fn] = bytes(val)
        elif wt == 0:
            fields[fn] = int(val)
        else:
            fields[fn] = val

    if 1 in fields:
        li.id = bytes(fields[1]).decode("utf-8", "replace")
    if 8 in fields:
        li.name = _decode_text(bytes(fields[8]))
    li.opacity = float(_f32(fields[2])) if 2 in fields else 1.0
    li.visible_present = 4 in fields
    li.visible = bool(fields.get(4, 0))
    li.blend_mode = int(fields.get(5, 0))
    li.clip_type = int(fields.get(9, 0))
    li.clip_group = _as_int32(int(fields.get(10, 0)))
    li.layer_no = _as_int32(int(fields.get(11, 0)))
    li.is_group = bool(fields.get(13, 0))
    li.is_lock = bool(fields.get(3, 0))
    li.is_lock_alpha = bool(fields.get(7, 0))
    if 15 in fields:
        li.parent_id = bytes(fields[15]).decode("utf-8", "replace")
    return li


def _parse_mp_layers(buf: bytes) -> list[LayerInfo]:
    return [_parse_layer_info(bytes(val)) for fn, wt, val in _iter_fields(buf)
            if fn == 1 and wt == 2]


def parse_draw_data(buf: bytes) -> DrawData:
    """解析 paint.dat / paint_as.dat 中的 DrawData。"""
    data = DrawData()
    map_layers: dict[str, list[LayerInfo]] = {}
    direct_layers: list[LayerInfo] = []

    for fn, wt, val in _iter_fields(buf):
        if fn == 3 and wt == 0:
            data.bg_color = _as_int32(int(val))
        elif fn == 4 and wt == 0:
            data.layer_count = int(val)
        elif fn == 5 and wt == 0:
            data.canvas_width = int(val)
        elif fn == 6 and wt == 0:
            data.canvas_height = int(val)
        elif fn == 10 and wt == 0:
            data.bg_hidden = bool(val)
        elif fn == 30 and wt == 0:
            data.ppi = int(val) or 72
        elif fn == 39 and wt == 2:
            data.color_space = bytes(val).decode("utf-8", "replace")
        elif fn == 20 and wt == 2:
            key = ""
            layers: list[LayerInfo] = []
            for f2, w2, v2 in _iter_fields(bytes(val)):
                if f2 == 1 and w2 == 2:
                    key = bytes(v2).decode("utf-8", "replace")
                elif f2 == 2 and w2 == 2:
                    layers = _parse_mp_layers(bytes(v2))
            map_layers[key] = layers
        elif fn == 2 and wt == 2:
            # 兼容旧版：DrawData.layers
            direct_layers.append(_parse_layer_info(bytes(val)))

    if map_layers:
        if "0" in map_layers:
            data.layers = map_layers["0"]
        else:
            data.layers = max(map_layers.values(), key=len)
    else:
        data.layers = direct_layers

    def walk(items: list[LayerInfo]):
        for item in items:
            yield item
            yield from walk(item.children)

    all_layers = list(walk(data.layers))
    # 若整个文件里没有任何显式 visible 字段，通常意味着旧版默认全部可见
    if all_layers and not any(l.visible_present for l in all_layers):
        for l in all_layers:
            l.visible = True

    def default_names(items: list[LayerInfo]):
        for i, item in enumerate(items):
            if not item.name:
                item.name = f"图层 {i + 1}"
            default_names(item.children)

    default_names(data.layers)
    return data


# ---------------------------------------------------------------------------
# 图层像素
# ---------------------------------------------------------------------------

def layer_canvas_size(data: bytes) -> tuple[int, int]:
    """只读取图层文件头中的画布尺寸。"""
    _ver, w, h, _bbox = _parse_layer_header(data)
    return w, h


def _parse_layer_header(data: bytes) -> tuple[int, int, int, tuple[int, int, int, int]]:
    if len(data) < 32 or data[:4] != LAYER_MAGIC:
        raise HsjError("不是有效的画世界图层数据")
    version = int.from_bytes(data[4:7], "big")
    width = int.from_bytes(data[7:11], "big")
    height = int.from_bytes(data[11:15], "big")
    bbox = struct.unpack(">IIII", data[16:32])
    if not (0 < width <= 100000 and 0 < height <= 100000):
        raise HsjError(f"图层尺寸异常: {width}x{height}")
    return version, width, height, bbox


def _iter_lz4_strips(data: bytes) -> Iterator[tuple[int, int, int, int, np.ndarray]]:
    """版本 1：0x64 起是连续的 [24字节头 + LZ4 block]。"""
    pos = 0x64
    n = len(data)
    while pos + 24 <= n:
        usize, csize, x, y, w, h = struct.unpack(">IIIIII", data[pos:pos + 24])
        if usize == 0 or csize == 0:
            break
        if pos + 24 + csize > n:
            break
        comp = data[pos + 24:pos + 24 + csize]
        try:
            raw = lz4.block.decompress(comp, uncompressed_size=usize)
        except Exception as exc:
            raise HsjError(f"LZ4 图层数据解压失败: {exc}") from exc
        if h <= 0 or len(raw) % (h * 4):
            raise HsjError("LZ4 图层数据尺寸不一致")
        sw = len(raw) // (h * 4)
        yield x, y, sw, h, np.frombuffer(raw, dtype=np.uint8).reshape(h, sw, 4)
        pos += 24 + csize
        if pos >= n:
            break


def _iter_zstd_strips(data: bytes) -> Iterator[tuple[int, int, int, int, np.ndarray]]:
    """版本 2：与版本 1 相同的 [24字节头 + Zstd 帧] 重复结构。"""
    pos = 0x64
    n = len(data)
    while pos + 24 <= n:
        usize, csize, x, y, w, h = struct.unpack(">IIIIII", data[pos:pos + 24])
        if usize == 0 or csize == 0:
            break
        if pos + 24 + csize > n:
            break
        comp = data[pos + 24:pos + 24 + csize]
        dobj = zstandard.ZstdDecompressor().decompressobj()
        try:
            raw = dobj.decompress(comp)
        except zstandard.ZstdError as exc:
            raise HsjError(f"Zstd 图层数据解压失败: {exc}") from exc
        if not dobj.eof:
            raise HsjError("Zstd 帧不完整")
        if h <= 0 or len(raw) % (h * 4):
            raise HsjError("Zstd 图层数据尺寸不一致")
        sw = len(raw) // (h * 4)
        yield x, y, sw, h, np.frombuffer(raw, dtype=np.uint8).reshape(h, sw, 4)
        pos += 24 + csize


def decode_layer(data: bytes) -> np.ndarray:
    """把 layers/<uuid> 解码成 HxWx4 的 RGBA 数组（直通 alpha）。"""
    version, canvas_w, canvas_h, _bbox = _parse_layer_header(data)
    canvas = np.zeros((canvas_h, canvas_w, 4), dtype=np.uint8)

    if version == 1:
        strips = _iter_lz4_strips(data)
    elif version == 2:
        strips = _iter_zstd_strips(data)
    else:
        raise HsjError(f"不支持的图层版本: {version}")

    for x, y, sw, sh, arr in strips:
        # 原始像素行序是自下而上
        arr = arr[::-1]
        # 条带头的 y 使用“底部为原点”的坐标
        top = canvas_h - (y + sh)
        left = x
        x0 = max(0, left)
        y0 = max(0, top)
        x1 = min(canvas_w, left + sw)
        y1 = min(canvas_h, top + sh)
        if x1 <= x0 or y1 <= y0:
            continue
        canvas[y0:y1, x0:x1] = arr[y0 - top:y1 - top, x0 - left:x1 - left]
    return canvas


# ---------------------------------------------------------------------------
# 图层树
# ---------------------------------------------------------------------------

def build_layer_tree(layers: list[LayerInfo]) -> list[LayerInfo]:
    """返回根节点列表；列表顺序为自下而上。"""
    if not layers:
        return []
    by_id = {l.id: l for l in layers if l.id}
    has_parent = any(l.parent_id for l in layers)
    has_nested = any(l.children for l in layers)
    if not has_parent and not has_nested:
        return layers

    if has_nested:
        # children 里可能已经包含子节点；把列表中重复出现的子节点剔除
        child_ids = set()

        def mark(node: LayerInfo):
            for c in node.children:
                child_ids.add(c.id)
                mark(c)
        for l in layers:
            if l.is_group:
                mark(l)
        roots = [l for l in layers if l.id not in child_ids]
        return roots or layers

    # 只有 parentId 的扁平表示
    roots = []
    children_map: dict[str, list[LayerInfo]] = {}
    for l in layers:
        if l.parent_id and l.parent_id in by_id:
            children_map.setdefault(l.parent_id, []).append(l)
        else:
            roots.append(l)
    for l in layers:
        if l.id in children_map:
            l.children = children_map[l.id]
            l.is_group = True
    return roots or layers


def flatten_for_psd(
    roots: list[LayerInfo],
    prefix: str = "",
    parent_opacity: float = 1.0,
    parent_visible: bool = True,
) -> list[tuple[LayerInfo, str, float, bool]]:
    """把图层树展开成自下而上的扁平列表。

    返回 (layer, 完整名称, 有效不透明度, 有效可见性)。
    组不透明度会近似乘到子图层上（PSD 扁平化输出）。
    """
    out: list[tuple[LayerInfo, str, float, bool]] = []
    for l in roots:
        if l.is_group:
            gname = l.name or "组"
            out.extend(flatten_for_psd(
                l.children,
                f"{prefix}{gname}/",
                parent_opacity * l.opacity,
                parent_visible and l.visible,
            ))
        else:
            leaf_name = l.name or "图层"
            out.append((
                l,
                prefix + leaf_name,
                parent_opacity * l.opacity,
                parent_visible and l.visible,
            ))
    return out
