"""Read the skin of a .glb without Blender: bone count and bone influences per vertex."""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_COMP = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2), 5123: ("H", 2), 5125: ("I", 4),
         5126: ("f", 4)}
_TYPES = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
_NORM = {5121: 255.0, 5123: 65535.0}


@dataclass
class SkinInfo:
    bones: int
    vertices: int
    max_influences: int
    unweighted_vertices: int


def _load(path: Path) -> tuple[dict, bytes]:
    data = Path(path).read_bytes()
    magic, version, _ = struct.unpack_from("<III", data, 0)
    if magic != 0x46546C67 or version != 2:
        raise ValueError("not a .glb file")
    jlen = struct.unpack_from("<I", data, 12)[0]
    gltf = json.loads(data[20:20 + jlen])
    blen = struct.unpack_from("<I", data, 20 + jlen)[0]
    start = 20 + jlen + 8
    return gltf, data[start:start + blen]


def _accessor(gltf: dict, blob: bytes, idx: int) -> np.ndarray:
    acc = gltf["accessors"][idx]
    view = gltf["bufferViews"][acc["bufferView"]]
    fmt, size = _COMP[acc["componentType"]]
    n = _TYPES[acc["type"]]
    stride = view.get("byteStride") or size * n
    base = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    out = np.empty((acc["count"], n), dtype=np.float64)
    for i in range(acc["count"]):
        out[i] = struct.unpack_from("<" + fmt * n, blob, base + i * stride)
    if acc.get("normalized") and acc["componentType"] in _NORM:
        out /= _NORM[acc["componentType"]]
    return out


def read_skin(path: Path) -> SkinInfo:
    """Bones of the first skin, and the most bones any vertex follows (counting every
    JOINTS_n/WEIGHTS_n set, so a file with 8 weights per vertex reports up to 8)."""
    gltf, blob = _load(path)
    skins = gltf.get("skins", [])
    bones = len(skins[0]["joints"]) if skins else 0
    max_inf, unweighted, verts = 0, 0, 0
    for mesh in gltf.get("meshes", []):
        for prim in mesh["primitives"]:
            attrs = prim["attributes"]
            sets = sorted(k for k in attrs if k.startswith("WEIGHTS_"))
            if not sets:
                continue
            w = np.concatenate([_accessor(gltf, blob, attrs[k]) for k in sets], axis=1)
            counts = (w > 1e-6).sum(axis=1)
            verts += len(w)
            max_inf = max(max_inf, int(counts.max()) if len(counts) else 0)
            unweighted += int((w.sum(axis=1) <= 1e-6).sum())
    return SkinInfo(bones, verts, max_inf, unweighted)


def _array(gltf: dict, blob: bytes, idx: int) -> np.ndarray:
    """Vectorised accessor read (any stride), for big meshes."""
    acc = gltf["accessors"][idx]
    view = gltf["bufferViews"][acc["bufferView"]]
    fmt, size = _COMP[acc["componentType"]]
    n = _TYPES[acc["type"]]
    stride = view.get("byteStride") or size * n
    base = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    dt = np.dtype("<" + fmt)
    count = acc["count"]
    if count == 0:
        return np.zeros((0, n))
    raw = np.frombuffer(blob, dtype=np.uint8, count=(count - 1) * stride + size * n,
                        offset=base)
    rows = np.lib.stride_tricks.as_strided(raw, shape=(count, size * n), strides=(stride, 1))
    out = np.ascontiguousarray(rows).view(dt).reshape(count, n).astype(np.float64)
    if acc.get("normalized") and acc["componentType"] in _NORM:
        out /= _NORM[acc["componentType"]]
    return out


def _node_matrix(node: dict) -> np.ndarray:
    if "matrix" in node:
        return np.array(node["matrix"], float).reshape(4, 4).T
    m = np.eye(4)
    x, y, z, w = node.get("rotation", [0, 0, 0, 1])
    r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    m[:3, :3] = r * np.array(node.get("scale", [1, 1, 1]), float)
    m[:3, 3] = node.get("translation", [0, 0, 0])
    return m


def read_mesh(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Every triangle of the default scene, as (vertices, triangles) in Blender's frame
    (metres, Z up; glTF +Z front becomes -Y), node transforms applied."""
    gltf, blob = _load(path)
    verts, tris, base = [], [], 0
    scene = gltf.get("scenes", [{}])[gltf.get("scene", 0)]
    roots = scene.get("nodes", list(range(len(gltf.get("nodes", [])))))
    stack = [(i, np.eye(4)) for i in roots]
    while stack:
        i, parent = stack.pop()
        node = gltf["nodes"][i]
        m = parent @ _node_matrix(node)
        stack += [(c, m) for c in node.get("children", [])]
        if "mesh" not in node:
            continue
        for prim in gltf["meshes"][node["mesh"]]["primitives"]:
            if prim.get("mode", 4) != 4:
                continue
            p = _array(gltf, blob, prim["attributes"]["POSITION"])
            p = p @ m[:3, :3].T + m[:3, 3]
            if "indices" in prim:
                t = _array(gltf, blob, prim["indices"]).astype(np.int64).reshape(-1, 3)
            else:
                t = np.arange(len(p) - len(p) % 3).reshape(-1, 3)
            verts.append(p)
            tris.append(t + base)
            base += len(p)
    if not verts:
        raise ValueError("the file has no mesh")
    v = np.vstack(verts)
    return np.stack([v[:, 0], -v[:, 2], v[:, 1]], axis=1), np.vstack(tris)
