"""Blender (headless) script: bake a humanoid animation library into a small JSON.

    blender -b --factory-startup -P blender/bake_library.py -- LIB.glb LIB_RM.glb OUT.json

Reads the Quaternius Universal Animation Library (CC0; Unreal-Godot/UAL1_Standard.glb for the
poses, UAL1_Standard_RM.glb for the ground speed of the walking clips) and writes, for each
wanted clip and each frame, every mapped bone's world turn away from its rest orientation
(quaternion, armature axes) and the pelvis's move from rest. `asset_forge.animate.library`
re-targets that onto any rigged humanoid. Run once; the JSON is committed, the zip is not.
"""

import json
import sys
from pathlib import Path

import bpy
import numpy as np

# source bone -> (our bone, source bone it points at)
MAP = {
    "pelvis": ("Hips", "spine_01"), "spine_01": ("Spine", "spine_02"),
    "spine_02": ("Chest", "spine_03"), "spine_03": ("UpperChest", "neck_01"),
    "neck_01": ("Neck", "Head"), "Head": ("Head", None),
    "clavicle_l": ("LeftShoulder", "upperarm_l"), "upperarm_l": ("LeftUpperArm", "lowerarm_l"),
    "lowerarm_l": ("LeftLowerArm", "hand_l"), "hand_l": ("LeftHand", "middle_01_l"),
    "clavicle_r": ("RightShoulder", "upperarm_r"), "upperarm_r": ("RightUpperArm", "lowerarm_r"),
    "lowerarm_r": ("RightLowerArm", "hand_r"), "hand_r": ("RightHand", "middle_01_r"),
    "thigh_l": ("LeftUpperLeg", "calf_l"), "calf_l": ("LeftLowerLeg", "foot_l"),
    "foot_l": ("LeftFoot", "ball_l"), "ball_l": ("LeftToes", "ball_leaf_l"),
    "thigh_r": ("RightUpperLeg", "calf_r"), "calf_r": ("RightLowerLeg", "foot_r"),
    "foot_r": ("RightFoot", "ball_r"), "ball_r": ("RightToes", "ball_leaf_r"),
}
# library clip -> our clip name (a clip may be listed twice, e.g. for two attacks)
WANTED = {"Idle_Loop": "idle", "Walk_Loop": "walk", "Jog_Fwd_Loop": "run",
          "Sprint_Loop": "sprint", "Punch_Jab": "punch_jab", "Punch_Cross": "punch_cross",
          "Sword_Attack": "sword", "Hit_Chest": "hit", "Hit_Head": "hit_head",
          "Death01": "faint"}
LOOPS = ("idle", "walk", "run", "sprint")
SRC_FPS = 24  # the importer turns seconds into frames at the scene rate (24 here)


def use_action(arm, act):
    ad = arm.animation_data or arm.animation_data_create()
    ad.action = act
    if hasattr(ad, "action_slot") and len(act.slots):
        ad.action_slot = act.slots[0]


def load(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.fps = SRC_FPS
    bpy.ops.import_scene.gltf(filepath=path)
    return next(o for o in bpy.data.objects if o.type == "ARMATURE")


def rest_info(arm):
    out = {}
    for s, (ours, pointing) in MAP.items():
        b = arm.data.bones[s]
        head = np.array(b.head_local[:])
        tail = np.array(arm.data.bones[pointing].head_local[:]) if pointing else np.array(
            b.tail_local[:])
        out[s] = {"ours": ours, "head": head.round(6).tolist(),
                  "dir": ((tail - head) / np.linalg.norm(tail - head)).round(6).tolist()}
    return out


def mat_to_quat(m):
    from mathutils import Matrix
    return Matrix(m.tolist()).to_quaternion()


def bake(arm, speeds):
    rests = {s: np.array([list(r) for r in arm.data.bones[s].matrix_local.to_3x3()]) for s in MAP}
    clips = {}
    for act in bpy.data.actions:
        if act.name not in WANTED:
            continue
        name = WANTED[act.name]
        use_action(arm, act)
        f0, f1 = int(act.frame_range[0]), int(act.frame_range[1])
        q = {s: [] for s in MAP}
        hips = []
        rest_pelvis = np.array(arm.data.bones["pelvis"].head_local[:])
        for f in range(f0, f1 + 1):
            bpy.context.scene.frame_set(f)
            for s in MAP:
                pb = arm.pose.bones[s]
                R = np.array([list(r) for r in pb.matrix.to_3x3().normalized()])
                qq = mat_to_quat(R @ rests[s].T)
                if q[s] and np.dot(q[s][-1], list(qq)) < 0:
                    qq.negate()
                q[s].append([round(v, 6) for v in qq])
            moved = np.array(arm.pose.bones["pelvis"].head[:]) - rest_pelvis
            hips.append(moved.round(6).tolist())
        clips[name] = {"frames": f1 - f0 + 1, "fps": SRC_FPS, "loop": name in LOOPS,
                       "speed_m_s": speeds.get(name, 0.0), "q": q, "hips": hips}
    return clips


def root_speeds(path):
    """Forward ground speed (m/s) of each wanted looping clip, from the root-motion file."""
    arm = load(path)
    out = {}
    for act in bpy.data.actions:
        name = WANTED.get(act.name)
        if name not in LOOPS:
            continue
        use_action(arm, act)
        f0, f1 = int(act.frame_range[0]), int(act.frame_range[1])
        pts = []
        for f in (f0, f1):
            bpy.context.scene.frame_set(f)
            pts.append(np.array(arm.pose.bones["root"].head[:]))
        out[name] = round(float(np.linalg.norm(pts[1] - pts[0])) / ((f1 - f0) / SRC_FPS), 4)
    return out


def main():
    a = sys.argv[sys.argv.index("--") + 1:]
    speeds = root_speeds(a[1])
    arm = load(a[0])
    data = {"source": "Quaternius Universal Animation Library [Standard] v3.0 (CC0 1.0)",
            "url": "https://quaternius.itch.io/universal-animation-library",
            "fps": SRC_FPS, "height_m": round(float(max(
                b.tail_local[2] for b in arm.data.bones)), 4),
            "bones": rest_info(arm), "clips": bake(arm, speeds)}
    Path(a[2]).write_text(json.dumps(data, separators=(",", ":")))
    print("BAKE_OK", {k: (v["frames"], v["speed_m_s"]) for k, v in data["clips"].items()})


main()
