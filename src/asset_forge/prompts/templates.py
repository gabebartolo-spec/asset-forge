"""Fixed wording per asset type. The model only writes the subject; the view, pose and
background words are added here, so they are always present and never reworded."""

from __future__ import annotations

ASSET_TYPES = ("humanoid", "monster", "animal", "sprite")
TARGETS = ("front", "back")

MAX_SUBJECT_CHARS = 240
MAX_PROMPT_CHARS = 480

_SUBJECT_RULES = (
    "You write the subject line of an image prompt for a game art tool. Reply with ONE line, "
    "at most 35 words, in plain English: who or what it is, body shape, clothing or colours, "
    "and one or two distinctive features. Keep every feature the user names (counts of arms, "
    "legs, heads, eyes included). Do not mention camera, pose, background, style or lighting. "
    "Do not invent extra body parts, and do not copy the example. "
    "No quotes, no lists, no preamble."
)

SYSTEM = {
    "humanoid": _SUBJECT_RULES
    + " The subject is a humanoid with two arms and two legs unless the idea says otherwise.",
    "monster": _SUBJECT_RULES + " The subject is a monster or creature; keep its limb count exact.",
    "animal": _SUBJECT_RULES
    + " The subject is a real animal with its natural body (legs, wings, tail as in life).",
    "sprite": _SUBJECT_RULES
    + " The subject is a single creature or character for a pixel-art sprite.",
}

# Fixed view words: (asset_type, target) -> suffix.
SUFFIX = {
    ("humanoid", "front"): "full body, front view, standing in a T-pose, arms straight out, "
    "plain white background, centred, even lighting",
    ("monster", "front"): "full body, front view, symmetrical standing pose with limbs clear of "
    "the body, plain white background, centred, even lighting",
    ("animal", "front"): "full body, side-on view, standing on all fours, four legs clearly "
    "visible, plain white background, centred, even lighting",
    ("sprite", "front"): "pixel art sprite, full body, front view facing the viewer, "
    "plain flat background, centred, clean outline, limited palette",
    ("sprite", "back"): "pixel art sprite, full body, seen from directly behind, turned away "
    "from the viewer, back and rump visible, face hidden, plain flat background, centred, "
    "clean outline, limited palette",
}

FEWSHOT = {
    "humanoid": (
        "desert nomad",
        "A weathered desert nomad in a sand-coloured hooded cloak and a blue face scarf, "
        "carrying a curved knife and a water flask.",
    ),
    "monster": (
        "swamp ogre",
        "A hunched green ogre with a wide belly, two thick arms, a flat tusked face and a "
        "ragged cloth belt.",
    ),
    "animal": (
        "red panda",
        "A red panda with rusty-red fur, a white-marked face, dark legs and a long ringed tail.",
    ),
    "sprite": (
        "moss turtle",
        "A small turtle with a mossy green shell, short stubby legs and calm round eyes.",
    ),
}
