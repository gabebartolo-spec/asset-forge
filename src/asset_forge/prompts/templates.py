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
    "No quotes, no lists, no preamble."
)

SYSTEM = {
    "humanoid": _SUBJECT_RULES + " The subject is a two-legged humanoid character.",
    "monster": _SUBJECT_RULES + " The subject is a monster or creature; keep its limb count exact.",
    "animal": _SUBJECT_RULES
    + " The subject is a real-world style animal with a simple low-poly friendly look.",
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
        "a space pirate",
        "A lean space pirate in a patched red coat and a brass breathing mask, with a robotic "
        "left hand and heavy boots.",
    ),
    "monster": (
        "six-armed brute",
        "A hulking grey-skinned brute with six thick muscular arms, a broad horned head and a "
        "torn leather loincloth.",
    ),
    "animal": (
        "robin",
        "A small round robin with an orange-red breast, brown back, thin legs and a short "
        "dark beak.",
    ),
    "sprite": (
        "fire fox",
        "A small fox with an ember-orange coat, a flame-tipped tail and bright yellow eyes.",
    ),
}
