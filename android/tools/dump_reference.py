#!/usr/bin/env python3
"""Generate metadata + layer pixel hashes from the verified Python converter.

Used by the Kotlin JVM parity tests. Run from the project root:
    python android/tools/dump_reference.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from hsj2psd import load_draft  # noqa: E402
from hsjconv import flatten_for_psd, load_hsj  # noqa: E402

SAMPLES = ("图像.hsj", "模板稿1.hsj", "test47.hsj")
OUT = ROOT / "android" / "build" / "reference"


def serialize_tree(items) -> list[dict]:
    out = []
    for item in items:
        out.append({
            "id": item.id,
            "name": item.name,
            "opacity": item.opacity,
            "visible": item.visible,
            "blendMode": item.blend_mode,
            "clipType": item.clip_type,
            "clipGroup": item.clip_group,
            "layerNo": item.layer_no,
            "isGroup": item.is_group,
            "isLock": item.is_lock,
            "isLockAlpha": item.is_lock_alpha,
            "children": serialize_tree(item.children),
        })
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name in SAMPLES:
        path = ROOT / "samples" / name
        if not path.exists():
            print("missing sample:", path)
            continue
        data = load_draft(str(path), with_bg=False, load_pixels=True,
                          log=lambda _msg: None)
        flat = flatten_for_psd(data["roots"])
        leaves = []
        for layer, flat_name, effective_opacity, effective_visible in flat:
            pixels = np.ascontiguousarray(layer.pixels)
            digest = hashlib.sha256(pixels.tobytes(order="C")).hexdigest()
            leaves.append({
                "id": layer.id,
                "name": layer.name,
                "flatName": flat_name,
                "opacity": layer.opacity,
                "visible": layer.visible,
                "effectiveOpacity": effective_opacity,
                "effectiveVisible": effective_visible,
                "blendMode": layer.blend_mode,
                "clipType": layer.clip_type,
                "clipGroup": layer.clip_group,
                "isLock": layer.is_lock,
                "isLockAlpha": layer.is_lock_alpha,
                "isGroup": layer.is_group,
                "pixelsSha256": digest,
                "pixelsShape": list(pixels.shape),
            })
        pkg = load_hsj(str(path))
        draw = data["draw"]
        meta = {
            "sample": name,
            "folderName": pkg.folder_name,
            "paintName": data["paint_name"],
            "canvasWidth": data["width"],
            "canvasHeight": data["height"],
            "ppi": draw.ppi,
            "colorSpace": draw.color_space,
            "bgArgb": draw.bg_color,
            "bgHidden": draw.bg_hidden,
            "tree": serialize_tree(data["roots"]),
            "leaves": leaves,
        }
        out = OUT / (path.stem + ".json")
        out.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{name}: {len(leaves)} leaves, {data['width']}x{data['height']} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
