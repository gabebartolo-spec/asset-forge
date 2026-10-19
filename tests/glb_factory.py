"""Tiny .glb writers for the export tests (no Blender needed)."""

import json
import struct
from pathlib import Path


def write_cube_glb(path: Path) -> Path:
    pos = [(-.5, -.5, -.5), (.5, -.5, -.5), (.5, .5, -.5), (-.5, .5, -.5),
           (-.5, -.5, .5), (.5, -.5, .5), (.5, .5, .5), (-.5, .5, .5)]
    idx = [0, 2, 1, 0, 3, 2, 4, 5, 6, 4, 6, 7, 0, 1, 5, 0, 5, 4,
           2, 3, 7, 2, 7, 6, 1, 2, 6, 1, 6, 5, 3, 0, 4, 3, 4, 7]
    pbin = b"".join(struct.pack("<3f", *p) for p in pos)
    ibin = struct.pack(f"<{len(idx)}H", *idx)
    ibin += b"\0" * (-len(ibin) % 4)
    gltf = {
        "asset": {"version": "2.0"},
        "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0, "name": "Cube"}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
        "buffers": [{"byteLength": len(pbin) + len(ibin)}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(pbin), "target": 34962},
                        {"buffer": 0, "byteOffset": len(pbin), "byteLength": len(ibin),
                         "target": 34963}],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 8, "type": "VEC3",
             "min": [-.5, -.5, -.5], "max": [.5, .5, .5]},
            {"bufferView": 1, "componentType": 5123, "count": len(idx), "type": "SCALAR"}],
    }
    return _pack(path, gltf, pbin + ibin)


def _pack(path: Path, gltf: dict, binary: bytes) -> Path:
    js = json.dumps(gltf).encode()
    js += b" " * (-len(js) % 4)
    total = 12 + 8 + len(js) + 8 + len(binary)
    path.write_bytes(
        struct.pack("<III", 0x46546C67, 2, total)
        + struct.pack("<II", len(js), 0x4E4F534A) + js
        + struct.pack("<II", len(binary), 0x004E4942) + binary)
    return path


def write_broken_glb(path: Path) -> Path:
    """Valid container, but the buffer is cut short of what the accessors declare."""
    good = write_cube_glb(path)
    data = good.read_bytes()
    jlen = struct.unpack_from("<I", data, 12)[0]
    gltf = json.loads(data[20:20 + jlen])
    return _pack(path, gltf, data[20 + jlen + 8:][:40])
