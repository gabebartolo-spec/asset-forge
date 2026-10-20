"""The fixed skeletons: bone names, parents and which joint each bone starts and ends at.

A joint is a name in the dict the fitter returns; a bone runs from its own joint (its head) to
`tail` (another joint). Names follow Godot's SkeletonProfileHumanoid for the humanoid so the
humanoid retarget profile maps it. Left is the character's left: +X when the model faces -Y.
"""

from __future__ import annotations

from dataclasses import dataclass

MAX_BONES = 64
MAX_INFLUENCES = 4


@dataclass(frozen=True)
class BoneDef:
    name: str
    parent: str | None
    tail: str  # joint name where the bone ends


def _side(prefix_l: str, prefix_r: str, spec: list[tuple[str, str | None, str]]) -> list[BoneDef]:
    """Expand a one-sided chain list into left and right copies ('{}' becomes the side)."""
    out = []
    for pre in (prefix_l, prefix_r):
        for name, parent, tail in spec:
            out.append(BoneDef(name.format(pre), parent.format(pre) if parent else None,
                               tail.format(pre)))
    return out


HUMANOID: list[BoneDef] = [
    BoneDef("Root", None, "Hips"),
    BoneDef("Hips", "Root", "Spine"),
    BoneDef("Spine", "Hips", "Chest"),
    BoneDef("Chest", "Spine", "UpperChest"),
    BoneDef("UpperChest", "Chest", "Neck"),
    BoneDef("Neck", "UpperChest", "Head"),
    BoneDef("Head", "Neck", "HeadTop"),
] + _side("Left", "Right", [
    ("{}Shoulder", "UpperChest", "{}UpperArm"),
    ("{}UpperArm", "{}Shoulder", "{}LowerArm"),
    ("{}LowerArm", "{}UpperArm", "{}Hand"),
    ("{}Hand", "{}LowerArm", "{}HandTip"),
    ("{}UpperLeg", "Hips", "{}LowerLeg"),
    ("{}LowerLeg", "{}UpperLeg", "{}Foot"),
    ("{}Foot", "{}LowerLeg", "{}Toes"),
    ("{}Toes", "{}Foot", "{}ToesTip"),
])

FOUR_LEGGED: list[BoneDef] = [
    BoneDef("Root", None, "Hips"),
    BoneDef("Hips", "Root", "Spine"),
    BoneDef("Spine", "Hips", "Chest"),
    BoneDef("Chest", "Spine", "Neck1"),
    BoneDef("Neck1", "Chest", "Neck2"),
    BoneDef("Neck2", "Neck1", "Head"),
    BoneDef("Head", "Neck2", "HeadTip"),
    BoneDef("Tail1", "Hips", "Tail2"),
    BoneDef("Tail2", "Tail1", "Tail3"),
    BoneDef("Tail3", "Tail2", "Tail4"),
    BoneDef("Tail4", "Tail3", "TailTip"),
] + _side("Left", "Right", [
    ("Front{}UpperLeg", "Chest", "Front{}LowerLeg"),
    ("Front{}LowerLeg", "Front{}UpperLeg", "Front{}Foot"),
    ("Front{}Foot", "Front{}LowerLeg", "Front{}FootTip"),
    ("Hind{}UpperLeg", "Hips", "Hind{}LowerLeg"),
    ("Hind{}LowerLeg", "Hind{}UpperLeg", "Hind{}Foot"),
    ("Hind{}Foot", "Hind{}LowerLeg", "Hind{}FootTip"),
])

# Two-legged animal: same spine, neck and tail chain, wings where the front legs would be.
BIRD: list[BoneDef] = [
    BoneDef("Root", None, "Hips"),
    BoneDef("Hips", "Root", "Chest"),
    BoneDef("Chest", "Hips", "Neck1"),
    BoneDef("Neck1", "Chest", "Neck2"),
    BoneDef("Neck2", "Neck1", "Head"),
    BoneDef("Head", "Neck2", "HeadTip"),
    BoneDef("Tail1", "Hips", "Tail2"),
    BoneDef("Tail2", "Tail1", "TailTip"),
] + _side("Left", "Right", [
    ("{}Wing1", "Chest", "{}Wing2"),
    ("{}Wing2", "{}Wing1", "{}WingTip"),
    ("{}UpperLeg", "Hips", "{}LowerLeg"),
    ("{}LowerLeg", "{}UpperLeg", "{}Foot"),
    ("{}Foot", "{}LowerLeg", "{}FootTip"),
])

TEMPLATES = {"humanoid": HUMANOID, "four_legged": FOUR_LEGGED, "bird": BIRD}


def joint_names(template: str) -> list[str]:
    """Every joint of a template, in order, with the end-of-chain points last."""
    bones = TEMPLATES[template]
    heads = [b.name for b in bones]
    ends = []
    for b in bones:
        if b.tail not in heads and b.tail not in ends:
            ends.append(b.tail)
    return heads + ends
