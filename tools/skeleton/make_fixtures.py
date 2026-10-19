"""Blender (headless) script: build the two tiny test meshes in tests/fixtures/.

    blender -b --factory-startup -P tools/skeleton/make_fixtures.py -- tests/fixtures

blockman.glb: a box humanoid about 1.8 m tall, A-pose arms, feet on z=0, facing -Y.
blockfox.glb: a box four-legged animal with a head at -Y and a tail towards +Y.
Boxes overlap and are joined into one mesh, like a generator's output (several shells).
"""

import math
import sys
from pathlib import Path

import bpy


def box(name, centre, size, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=centre, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    o.scale = size
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return o


def finish(out):
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    bpy.ops.export_scene.gltf(filepath=str(out), export_format="GLB", use_selection=True,
                              export_yup=True)


def blockman(out):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    H = 1.8
    box("torso", (0, 0, 0.69 * H), (0.30 * H, 0.14 * H, 0.32 * H))
    box("hips", (0, 0, 0.50 * H), (0.22 * H, 0.12 * H, 0.10 * H))
    box("neck", (0, 0, 0.84 * H), (0.06 * H, 0.06 * H, 0.06 * H))
    box("head", (0, 0, 0.92 * H), (0.12 * H, 0.14 * H, 0.14 * H))
    for s in (1, -1):
        box("thigh", (s * 0.08 * H, 0, 0.40 * H), (0.08 * H, 0.09 * H, 0.26 * H))
        box("shin", (s * 0.08 * H, 0, 0.17 * H), (0.07 * H, 0.08 * H, 0.26 * H))
        box("foot", (s * 0.08 * H, -0.03 * H, 0.02 * H), (0.08 * H, 0.16 * H, 0.04 * H))
        box("arm", (s * 0.23 * H, 0, 0.62 * H), (0.06 * H, 0.07 * H, 0.34 * H),
            rot=(0, s * math.radians(14), 0))
        box("hand", (s * 0.29 * H, 0, 0.44 * H), (0.06 * H, 0.08 * H, 0.10 * H))
    finish(out)


def blockfox(out):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    box("body", (0, 0, 0.28), (0.12, 0.35, 0.16))
    box("head", (0, -0.24, 0.33), (0.08, 0.12, 0.10))
    box("tail", (0, 0.30, 0.22), (0.05, 0.28, 0.05))
    for x in (0.045, -0.045):
        for y in (-0.12, 0.12):
            box("leg", (x, y, 0.10), (0.03, 0.04, 0.20))
    finish(out)


def main():
    out = Path(sys.argv[sys.argv.index("--") + 1])
    out.mkdir(parents=True, exist_ok=True)
    blockman(out / "blockman.glb")
    blockfox(out / "blockfox.glb")


main()
