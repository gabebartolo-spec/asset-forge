"""The quick test poses: rotations about WORLD axes at each joint, applied in order, so a bad
weight (a collapsed knee, a stretched shoulder) shows before any animation exists.

World axes: X is the character's left, -Y is forward, Z is up. (bone, axis, degrees).
"""

from __future__ import annotations

TEST_POSES: dict[str, list[tuple[str, str, float]]] = {
    "humanoid": [
        ("LeftUpperArm", "Y", -70), ("LeftLowerArm", "Z", -40),
        ("RightUpperArm", "X", -45), ("RightLowerArm", "X", -45),
        ("LeftUpperLeg", "X", -35), ("LeftLowerLeg", "X", 55),
        ("RightUpperLeg", "Y", 20),
        ("Spine", "Z", 15), ("Chest", "X", -8), ("Head", "Z", -25),
    ],
    "four_legged": [
        ("FrontLeftUpperLeg", "X", -35), ("FrontLeftLowerLeg", "X", 55),
        ("HindRightUpperLeg", "X", 30), ("HindRightLowerLeg", "X", -30),
        ("Neck1", "X", 20), ("Head", "Z", 30),
        ("Tail1", "Z", 30), ("Tail2", "Z", 30), ("Tail3", "Z", 25),
        ("Spine", "Z", 8),
    ],
    "bird": [
        ("Neck1", "X", 15), ("Head", "Z", 40),
        ("Tail1", "X", 30),
        ("LeftWing1", "Z", -70), ("RightWing1", "Z", 40),
        ("LeftUpperLeg", "X", -40), ("LeftLowerLeg", "X", 55),
    ],
}
