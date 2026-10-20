"""A tiny skinned .glb writer for the Skeleton tests (no Blender needed)."""

import struct
from pathlib import Path

from glb_factory import _pack


def write_skinned_glb(path: Path, bones: int = 5, influences: int = 4) -> Path:
    """A one-triangle skinned mesh whose every vertex follows `influences` bones (JOINTS_0 and
    WEIGHTS_0 carry 4; a second JOINTS_1/WEIGHTS_1 set carries 4 more)."""
    pos = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
    sets = 2 if influences > 4 else 1
    blob = b"".join(struct.pack("<3f", *p) for p in pos)
    views = [{"buffer": 0, "byteOffset": 0, "byteLength": len(blob), "target": 34962}]
    accessors = [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3",
                  "min": [0, 0, 0], "max": [1, 1, 0]}]
    attrs = {"POSITION": 0}
    for s in range(sets):
        n = min(4, influences - 4 * s)
        joints = bytes(((s * 4 + k) % bones if k < n else 0) for _ in range(3) for k in range(4))
        weights = b"".join(struct.pack("<4f", *[(1.0 / n if k < n else 0.0) for k in range(4)])
                           for _ in range(3))
        for name, comp, data in (("JOINTS", 5121, joints), ("WEIGHTS", 5126, weights)):
            views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)})
            blob += data
            accessors.append({"bufferView": len(views) - 1, "componentType": comp, "count": 3,
                              "type": "VEC4"})
            attrs[f"{name}_{s}"] = len(accessors) - 1
    nodes = [{"mesh": 0, "skin": 0, "name": "Model"}] + [{"name": f"b{i}"} for i in range(bones)]
    gltf = {
        "asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0, 1]}], "nodes": nodes,
        "skins": [{"joints": list(range(1, bones + 1))}],
        "meshes": [{"primitives": [{"attributes": attrs}]}],
        "buffers": [{"byteLength": len(blob)}], "bufferViews": views, "accessors": accessors,
    }
    return _pack(path, gltf, blob)
